using System;
using System.Threading;
using System.Threading.Tasks;
using PlayniteCmdPal.Core;

namespace PlayniteCmdPal;

/// <summary>
/// Cross-cutting page plumbing: UI-thread notification marshaling and the weak, deferred
/// favorites-change refresh shared by the pages that show game lists.
/// </summary>
internal static class PageSupport
{
    /// <summary>
    /// Runs <paramref name="raise"/> on the UI synchronization context captured at page
    /// construction: posted when the caller is on another thread, inline when already on
    /// that context or when no context was captured. This keeps the Command Palette host
    /// processing notifications regardless of which thread raises them.
    /// </summary>
    public static void RaiseOnUiThread(SynchronizationContext? capturedContext, Action raise)
    {
        if (capturedContext is { } context && !ReferenceEquals(context, SynchronizationContext.Current))
        {
            context.Post(_ => raise(), null);
        }
        else
        {
            raise();
        }
    }

    /// <summary>
    /// Subscribes to favorites changes with a handler that keeps only a weak reference to
    /// the page and detaches itself once the page is collected, so the shared store cannot
    /// retain retired pages. The refresh is deferred until after ToggleFavoriteCommand.Invoke()
    /// returns and its toast is shown; it must never run synchronously inside command
    /// dispatch, which would nest host notifications and suppress the toast. The delay
    /// resumes on the captured UI synchronization context so the host processes the
    /// resulting items-changed notification. Pass a captureless (static) lambda or method
    /// group as <paramref name="refreshPage"/> so the handler cannot root the page either.
    /// </summary>
    public static EventHandler SubscribeToFavoritesChanges<T>(T page, Action<T> refreshPage) where T : class
    {
        var weakPage = new WeakReference<T>(page);
        EventHandler handler = null!;
        handler = (sender, args) =>
        {
            if (weakPage.TryGetTarget(out var target))
            {
                _ = RefreshAfterFavoriteChangeAsync(target, refreshPage);
            }
            else if (sender is FavoritesStore store)
            {
                store.FavoritesChanged -= handler;
            }
        };
        return handler;
    }

    private static async Task RefreshAfterFavoriteChangeAsync<T>(T page, Action<T> refreshPage)
    {
        await Task.Delay(50);
        refreshPage(page);
    }
}
