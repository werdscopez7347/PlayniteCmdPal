// Copyright (c) Microsoft Corporation
// The Microsoft Corporation licenses this file to you under the MIT license.
// See third-party/Microsoft-PowerToys-LICENSE.txt for the license text.

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

internal sealed partial class PlayniteCmdPalPage : DynamicListPage, IDisposable
{
    private readonly PlayniteCatalogAdapter _catalog = new();
    private readonly FavoritesStore _favorites = FavoritesPreferences.Store;
    private readonly ArtworkIconLoader _artwork = new(artworkId => PlayniteCatalogAdapter.ResolveArtworkPath(artworkId));
    private readonly CatalogFilterState _filterState = new();
    private readonly EventHandler _favoritesChangedHandler;
    private readonly SynchronizationContext? _uiContext;
    private readonly FiltersPage _filtersPage;
    private IListItem[] _items = [CreateStatusItem("Loading your Playnite library…")];
    private CancellationTokenSource? _searchCancellation;
    private string _searchText = string.Empty;
    private int _requestVersion;
    private readonly object _requestGate = new();
    private bool _disposed;

    public PlayniteCmdPalPage()
    {
        _uiContext = SynchronizationContext.Current;
        _filtersPage = new FiltersPage(_filterState, () => BeginSearch());

        Icon = IconHelpers.FromRelativePath("Assets\\StoreLogo.png");
        Title = "Playnite";
        Name = "Search games";

        // Keep Search Games in sync when a game is pinned or unpinned from any page.
        _favoritesChangedHandler = PageSupport.SubscribeToFavoritesChanges(this, static page => page.BeginSearch());
        _favorites.FavoritesChanged += _favoritesChangedHandler;

        BeginSearch();
    }

    public override void UpdateSearchText(string oldSearch, string newSearch)
    {
        BeginSearch(searchText: newSearch ?? string.Empty);
    }

    public override IListItem[] GetItems()
    {
        lock (_requestGate) return _items;
    }

    /// <summary>
    /// Raises the items-changed notification on the UI synchronization context so the
    /// Command Palette host processes it on the thread it expects.
    /// </summary>
    private void RaiseItemsChangedOnUIContext(int count) =>
        PageSupport.RaiseOnUiThread(_uiContext, () => RaiseItemsChanged(count));

    internal void RefreshCatalog()
    {
        BeginSearch(forceRefresh: true);
    }

    private void BeginSearch(bool forceRefresh = false, string? searchText = null)
    {
        int version;
        string query;
        CancellationToken cancellationToken;
        int count;

        lock (_requestGate)
        {
            if (_disposed)
                return;

            if (searchText is not null)
            {
                _searchText = searchText;
            }

            _searchCancellation?.Cancel();
            _searchCancellation?.Dispose();
            _searchCancellation = new CancellationTokenSource();

            version = ++_requestVersion;
            query = _searchText;
            cancellationToken = _searchCancellation.Token;

            _items = [CreateFiltersItem(), CreateStatusItem("Searching your Playnite library…")];
            count = _items.Length;
        }

        // Notify outside the request lock: the host may synchronously re-enter GetItems.
        RaiseItemsChangedOnUIContext(count);
        _ = LoadItemsAsync(version, query, forceRefresh, cancellationToken);
    }

    private async Task LoadItemsAsync(
        int version,
        string query,
        bool forceRefresh,
        CancellationToken cancellationToken)
    {
        int count = 0;
        try
        {
            var catalog = forceRefresh
                ? await _catalog.RefreshAsync(cancellationToken)
                : await _catalog.GetAsync(cancellationToken);

            cancellationToken.ThrowIfCancellationRequested();

            // A normal search/pin refresh reuses validated artwork. Only an explicit
            // catalog refresh should invalidate artwork references and force disk resolution.
            if (forceRefresh)
            {
                _artwork.Invalidate();
            }

            (IListItem[] Items, IReadOnlyList<(ListItem Item, GameEntry Game)> ArtworkItems) built;
            lock (_requestGate)
            {
                if (version != _requestVersion || cancellationToken.IsCancellationRequested)
                {
                    return;
                }

                // Do not reinterpret a transient unavailable catalog as an empty snapshot:
                // that would discard valid source/platform choices while the picker is open.
                if (catalog.IsAvailable)
                {
                    _filterState.UpdateCatalog(catalog.Games);
                }

                built = BuildItems(catalog, query);
                _items = built.Items;
                count = _items.Length;
            }

            RaiseItemsChangedOnUIContext(count);
            _ = LoadArtworkAsync(version, built.ArtworkItems, cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // A newer query or explicit refresh superseded this request.
        }
        catch (Exception)
        {
            lock (_requestGate)
            {
                if (version != _requestVersion || cancellationToken.IsCancellationRequested)
                {
                    return;
                }

                _items =
                [
                    CreateFiltersItem(),
                    CreateStatusItem("Couldn't read the Playnite catalog. Check the companion plugin and snapshot permissions, then refresh."),
                ];
            }

            count = _items.Length;
            RaiseItemsChangedOnUIContext(count);
        }
    }

    private (IListItem[] Items, IReadOnlyList<(ListItem Item, GameEntry Game)> ArtworkItems) BuildItems(CatalogReadResult catalog, string query)
    {
        var items = new List<IListItem> { CreateFiltersItem() };
        if (!catalog.IsAvailable)
        {
            var message = catalog.Issue?.Message
                ?? "The Playnite catalog is unavailable. Install and start the companion plugin, then refresh.";
            items.Add(CreateRefreshItem(message));
            return (items.ToArray(), Array.Empty<(ListItem Item, GameEntry Game)>());
        }
        if (catalog.IsStale)
        {
            items.Add(CreateStatusItem("The Playnite catalog is over 24 hours old. Open Playnite to refresh it."));
        }

        if (catalog.Issue is not null)
        {
            items.Add(CreateStatusItem("The latest catalog refresh failed. Showing the last valid snapshot; check the companion plugin and refresh."));
        }

        if (catalog.SkippedRecordCount > 0)
        {
            items.Add(CreateStatusItem($"{catalog.SkippedRecordCount} invalid catalog entr{(catalog.SkippedRecordCount == 1 ? "y was" : "ies were")} skipped."));
        }

        if (catalog.Games.Count == 0)
        {
            items.Add(CreateRefreshItem("Your Playnite library is empty. Add games in Playnite, then refresh."));
            return (items.ToArray(), Array.Empty<(ListItem Item, GameEntry Game)>());
        }

        var activeFilters = _filterState.ToSearchFilters();
        var matches = GameSearch.Search(catalog.Games, query, activeFilters);
        if (matches.Count == 0)
        {
            var hasActiveFilters = activeFilters.IsInstalled.HasValue
                || activeFilters.Sources?.Count > 0
                || activeFilters.Platforms?.Count > 0;
            var message = hasActiveFilters
                ? string.IsNullOrWhiteSpace(query)
                    ? "No games match the selected filters. Clear one or more filters to see more games."
                    : $"No games match “{query.Trim()}” with the selected filters. Clear a filter or change your search."
                : string.IsNullOrWhiteSpace(query)
                    ? "No games are available in the current catalog."
                    : $"No games match “{query.Trim()}”.";
            items.Add(CreateStatusItem(message));
            return (items.ToArray(), Array.Empty<(ListItem Item, GameEntry Game)>());
        }

        var duplicateIds = matches
            .GroupBy(game => game.Title, StringComparer.OrdinalIgnoreCase)
            .Where(group => group.Count() > 1)
            .SelectMany(group => group.Select(game => game.GameId))
            .ToHashSet(StringComparer.Ordinal);

        var artworkItems = new List<(ListItem Item, GameEntry Game)>();
        foreach (var game in matches)
        {
            var subtitle = BuildMetadata(
                game,
                includeInstalledState: true,
                includeIdTag: duplicateIds.Contains(game.GameId));
            var item = CreateGameRow(game, _favorites, subtitle);
            items.Add(item);
            artworkItems.Add((item, game));
        }

        return (items.ToArray(), artworkItems);
    }

    private async Task LoadArtworkAsync(
        int version,
        IReadOnlyList<(ListItem Item, GameEntry Game)> artworkItems,
        CancellationToken cancellationToken)
    {
        if (artworkItems.Count == 0) return;

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

                        var updated = false;
                        int itemsCount = 0;
                        lock (_requestGate)
                        {
                            // Do not mutate objects belonging to an obsolete search request.
                            if (version != _requestVersion || token.IsCancellationRequested)
                            {
                                return;
                            }

                            entry.Item.Icon = icon ?? ArtworkIconLoader.FallbackIcon;
                            updated = true;
                            itemsCount = _items.Length;
                        }

                        if (updated)
                        {
                            RaiseItemsChangedOnUIContext(itemsCount);
                        }
                    }
                    catch (OperationCanceledException) when (token.IsCancellationRequested)
                    {
                        throw;
                    }
                    catch (Exception)
                    {
                        // A failure for one row must not prevent artwork for other rows.
                    }
                }).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // A newer query replaced this result set.
        }
    }

    private ListItem CreateFiltersItem()
    {
        var count = _filterState.ActiveFilterCount;
        return new ListItem(_filtersPage)
        {
            Title = count == 0 ? "Filters" : $"Filters ({count})",
            Subtitle = count == 0 ? "Installed status · source · platform" : "Active · Select to edit",
            Icon = new IconInfo("\uE71C"),
        };
    }

    private ListItem CreateRefreshItem(string message) =>
        new ListItem(new RefreshCatalogCommand(RefreshCatalog)) { Title = message, Subtitle = "Press Enter to retry" };

    public void Dispose()
    {
        lock (_requestGate)
        {
            if (_disposed)
                return;

            _disposed = true;
            _requestVersion++;
            _searchCancellation?.Cancel();
            _searchCancellation?.Dispose();
            _searchCancellation = null;
        }

        _filtersPage.Dispose();
    }
}
