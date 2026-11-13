using System.Collections.Generic;
using Microsoft.CommandPalette.Extensions.Toolkit;
using PlayniteCmdPal.Core;

namespace PlayniteCmdPal;

/// <summary>
/// Shared builders for the rows the extension's game-list pages present, so every page
/// shapes titles, metadata, and row actions the same way.
/// </summary>
internal static class GameListItems
{
    private const string MetadataSeparator = " · ";

    public static ListItem CreateStatusItem(string message) =>
        new(new NoOpCommand()) { Title = message };

    public static ListItem CreateGameRow(GameEntry game, FavoritesStore favorites, string subtitle) =>
        new(new LaunchGameCommand(game.GameId))
        {
            Title = game.Title,
            Subtitle = subtitle,
            Icon = ArtworkIconLoader.FallbackIcon,
            MoreCommands =
            [
                new CommandContextItem(new ShowGameDetailsCommand(game.GameId)),
                new CommandContextItem(new ToggleFavoriteCommand(favorites, game.GameId)),
            ],
        };

    /// <summary>
    /// Builds the metadata subtitle shared by every game row: source, platform, install
    /// state (on pages that show it), and a short ID tag for disambiguating duplicates.
    /// </summary>
    public static string BuildMetadata(GameEntry game, bool includeInstalledState, bool includeIdTag)
    {
        var parts = new List<string>();
        if (!string.IsNullOrWhiteSpace(game.Source))
        {
            parts.Add(game.Source);
        }

        if (!string.IsNullOrWhiteSpace(game.Platform))
        {
            parts.Add(game.Platform);
        }

        if (includeInstalledState && game.IsInstalled.HasValue)
        {
            parts.Add(game.IsInstalled.Value ? "Installed" : "Not installed");
        }

        if (includeIdTag)
        {
            parts.Add($"ID {ShortGameId(game.GameId)}");
        }

        return string.Join(MetadataSeparator, parts);
    }

    public static string ShortGameId(string gameId) => gameId.Length > 8 ? gameId[..8] : gameId;
}
