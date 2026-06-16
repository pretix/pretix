def get_waiting_list_rank(entry):
    """
    Calculate a waiting-list entry's lottery rank.

    Will be moved from WaitingListEntry.get_rank() in Phase 2.
    """
    raise NotImplementedError


def run_lottery(event, item_id, *, revert=False):
    """
    Run or revert the waiting-list lottery for a product.

    Will be moved from control.views.waitinglist.EntryList._run_lottery()
    in Phase 2.
    """
    raise NotImplementedError
