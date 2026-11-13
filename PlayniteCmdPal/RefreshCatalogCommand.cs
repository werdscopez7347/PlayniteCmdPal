using System;
using Microsoft.CommandPalette.Extensions;
using Microsoft.CommandPalette.Extensions.Toolkit;

namespace PlayniteCmdPal;

/// <summary>Re-reads the Playnite catalog for the page that created it and keeps the palette open.</summary>
internal sealed partial class RefreshCatalogCommand : InvokableCommand
{
    private readonly Action _refreshCatalog;

    public RefreshCatalogCommand(Action refreshCatalog)
    {
        _refreshCatalog = refreshCatalog;
    }

    public override string Name => "Refresh Playnite catalog";

    public override CommandResult Invoke()
    {
        _refreshCatalog();
        return CommandResult.KeepOpen();
    }
}
