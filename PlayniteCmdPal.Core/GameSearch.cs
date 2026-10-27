namespace PlayniteCmdPal.Core;

/// <summary>
/// Performs case-insensitive title search with deterministic relevance and tie-break ordering.
/// </summary>
public static class GameSearch
{
    /// <summary>
    /// Searches a catalog by title. Ranking is exact, prefix, word-prefix, then substring.
    /// A null or whitespace query returns no results. Entries with the same game ID are
    /// represented once; distinct IDs with duplicate titles remain distinct results.
    /// </summary>
    /// <param name="catalog">Catalog entries supplied by the adapter.</param>
    /// <param name="query">User-entered title query.</param>
    /// <returns>A stable, read-only list of matching canonical entries.</returns>
    /// <exception cref="ArgumentNullException">Thrown when catalog is null.</exception>
    /// <exception cref="ArgumentException">Thrown when an entry has an invalid required field.</exception>
    public static IReadOnlyList<GameEntry> Search(IEnumerable<GameEntry> catalog, string? query)
    {
        ArgumentNullException.ThrowIfNull(catalog);

        if (string.IsNullOrWhiteSpace(query))
        {
            return Array.Empty<GameEntry>();
        }

        var normalizedQuery = query.Trim();
        var canonicalEntries = catalog
            .Select(entry => (entry ?? throw new ArgumentException("Catalog cannot contain null entries.", nameof(catalog))).Validate())
            .OrderBy(entry => entry.GameId, StringComparer.Ordinal)
            .ThenBy(entry => entry.Title, StringComparer.OrdinalIgnoreCase)
            .ThenBy(entry => entry.Title, StringComparer.Ordinal)
            .ThenBy(entry => entry.Source, StringComparer.Ordinal)
            .ThenBy(entry => entry.IsInstalled)
            .ThenBy(entry => entry.IconReference, StringComparer.Ordinal)
            .GroupBy(entry => entry.GameId, StringComparer.Ordinal)
            .Select(group => group.First());

        return canonicalEntries
            .Select(entry => new SearchResult(entry, GetMatchRank(entry.Title, normalizedQuery)))
            .Where(result => result.Rank >= 0)
            .OrderBy(result => result.Rank)
            .ThenBy(result => result.Entry.Title, StringComparer.OrdinalIgnoreCase)
            .ThenBy(result => result.Entry.Title, StringComparer.Ordinal)
            .ThenBy(result => result.Entry.GameId, StringComparer.Ordinal)
            .ThenBy(result => result.Entry.Source, StringComparer.Ordinal)
            .ThenBy(result => result.Entry.IsInstalled)
            .ThenBy(result => result.Entry.IconReference, StringComparer.Ordinal)
            .Select(result => result.Entry)
            .ToArray();
    }

    private static int GetMatchRank(string title, string query)
    {
        if (string.Equals(title, query, StringComparison.OrdinalIgnoreCase))
        {
            return 0;
        }

        if (title.StartsWith(query, StringComparison.OrdinalIgnoreCase))
        {
            return 1;
        }

        for (var index = 1; index < title.Length; index++)
        {
            if (!char.IsLetterOrDigit(title[index - 1])
                && char.IsLetterOrDigit(title[index])
                && title.AsSpan(index).StartsWith(query, StringComparison.OrdinalIgnoreCase))
            {
                return 2;
            }
        }

        return title.Contains(query, StringComparison.OrdinalIgnoreCase) ? 3 : -1;
    }

    private sealed record SearchResult(GameEntry Entry, int Rank);
}
