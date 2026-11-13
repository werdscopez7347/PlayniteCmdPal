using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.CommandPalette.Extensions;
using Microsoft.CommandPalette.Extensions.Toolkit;
using PlayniteCmdPal.Core;
using PlayniteCmdPal.Playnite;
using static PlayniteCmdPal.GameListItems;

namespace PlayniteCmdPal;

internal sealed partial class FavoritesPage : DynamicListPage
{
    private readonly PlayniteCatalogAdapter _catalog = new();
    private readonly FavoritesStore _favorites = FavoritesPreferences.Store;
    private readonly ArtworkIconLoader _artwork = new(artworkId => PlayniteCatalogAdapter.ResolveArtworkPath(artworkId));
    private readonly LatestRequestGate _requestGate = new();
    private readonly object _lifecycleGate = new();
    private readonly EventHandler _favoritesChangedHandler;
    private readonly SynchronizationContext? _uiContext;
    private CancellationTokenSource? _requestCancellation;
    private IListItem[] _items = [CreateStatusItem("Loading your favorites…")];
    private string _searchText = string.Empty;

    public FavoritesPage()
    {
        _uiContext = SynchronizationContext.Current;

        Icon = IconHelpers.FromRelativePath("Assets\\StoreLogo.png");
        Title = "Favorites";
        Name = "Pinned games";

        // The shared store must not keep retired page instances alive; the subscription
        // keeps only a weak reference to this page.
        _favoritesChangedHandler = PageSupport.SubscribeToFavoritesChanges(this, static page => page.LoadItems());
        _favorites.FavoritesChanged += _favoritesChangedHandler;
        LoadItems();
    }

    public override void UpdateSearchText(string oldSearch, string newSearch)
    {
        _requestGate.Synchronize(() => _searchText = newSearch ?? string.Empty);
        LoadItems();
    }

    public override IListItem[] GetItems() => _requestGate.Synchronize(() => _items);

    /// <summary>
    /// Raises the items-changed notification on the UI synchronization context so the
    /// Command Palette host processes it on the thread it expects.
    /// </summary>
    private void RaiseItemsChangedOnUIContext(int count) =>
        PageSupport.RaiseOnUiThread(_uiContext, () => RaiseItemsChanged(count));

    private void LoadItems()
    {
        CancellationToken token;
        (int Version, string State) request;
        int count;
        lock (_lifecycleGate)
        {
            _requestCancellation?.Cancel();
            _requestCancellation?.Dispose();
            _requestCancellation = new CancellationTokenSource();
            token = _requestCancellation.Token;
            request = _requestGate.BeginRequest(() =>
            {
                _items = [CreateStatusItem("Loading your favorites…")];
                return _searchText;
            });
            count = _items.Length;
        }

        RaiseItemsChangedOnUIContext(count);
        _ = LoadItemsAsync(request.Version, request.State, token);
    }

    private async Task LoadItemsAsync(int version, string query, CancellationToken cancellationToken)
    {
        try
        {
            var catalog = await _catalog.GetAsync(cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            if (!catalog.IsAvailable)
            {
                PublishIfCurrent(version,
                [
                    CreateStatusItem(catalog.Issue?.Message
                        ?? "The Playnite catalog is unavailable. Start Playnite and refresh.")
                ], cancellationToken);
                return;
            }

            var favoriteIds = _favorites.GetFavoriteIds().ToHashSet(StringComparer.Ordinal);
            var games = catalog.Games.Where(game => favoriteIds.Contains(game.GameId)).ToArray();
            var matches = GameSearch.Search(games, query);
            cancellationToken.ThrowIfCancellationRequested();

            if (matches.Count == 0)
            {
                var message = favoriteIds.Count == 0
                    ? "No favorites yet. Pin a game from its search result actions."
                    : "No saved favorites match this search in the current Playnite library.";
                PublishIfCurrent(version, [CreateStatusItem(message)], cancellationToken);
                return;
            }

            var items = new List<IListItem>();
            var artworkItems = new List<(ListItem Item, GameEntry Game)>();
            foreach (var game in matches)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var subtitle = BuildMetadata(game, includeInstalledState: true, includeIdTag: false);
                var item = CreateGameRow(game, _favorites, subtitle);
                items.Add(item);
                artworkItems.Add((item, game));
            }

            if (!PublishIfCurrent(version, items.ToArray(), cancellationToken))
            {
                return;
            }

            _ = LoadArtworkAsync(version, artworkItems, cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // A newer query or pin/unpin event superseded this request.
        }
        catch (Exception)
        {
            PublishIfCurrent(version,
            [
                CreateStatusItem("Couldn't load Favorites. Check the local preferences file and Playnite catalog, then try again.")
            ], cancellationToken);
        }
    }

    private async Task LoadArtworkAsync(
        int version,
        IReadOnlyList<(ListItem Item, GameEntry Game)> artworkItems,
        CancellationToken cancellationToken)
    {
        try
        {
            await Parallel.ForEachAsync(
                artworkItems,
                new ParallelOptions { MaxDegreeOfParallelism = 4, CancellationToken = cancellationToken },
                async (entry, token) =>
                {
                    try
                    {
                        var icon = await _artwork.GetIconAsync(entry.Game, token).ConfigureAwait(false);
                        token.ThrowIfCancellationRequested();
                        int itemsLength = 0;
                        var published = _requestGate.TryPublish(version, () =>
                        {
                            entry.Item.Icon = icon ?? ArtworkIconLoader.FallbackIcon;
                            itemsLength = _items.Length;
                        });
                        if (published) RaiseItemsChangedOnUIContext(itemsLength);
                    }
                    catch (OperationCanceledException) when (token.IsCancellationRequested)
                    {
                        throw;
                    }
                    catch (Exception)
                    {
                        // Artwork is optional; one bad image must not affect other favorites.
                    }
                }).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // A newer Favorites request cancelled obsolete artwork work.
        }
    }

    private bool PublishIfCurrent(int version, IListItem[] items, CancellationToken cancellationToken)
    {
        if (cancellationToken.IsCancellationRequested) return false;
        int count = 0;
        var published = _requestGate.TryPublish(version, () =>
        {
            _items = items;
            count = items.Length;
        });
        if (published) RaiseItemsChangedOnUIContext(count);
        return published;
    }
}
