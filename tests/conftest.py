import pytest
import tkinter as tk

_SHARED_TK_ROOT = None


@pytest.fixture(autouse=True)
def _shared_tkinter_root(monkeypatch):
    """Reuse a single withdrawn Tk root on Windows across GUI tests.

    Creating and destroying multiple tk.Tk() instances in the same process on Windows
    leads to STATUS_INVALID_HANDLE (0xc0000008) in Tcl's event notifier.
    """
    global _SHARED_TK_ROOT
    if _SHARED_TK_ROOT is None:
        try:
            _SHARED_TK_ROOT = tk.Tk()
            _SHARED_TK_ROOT.withdraw()
            _SHARED_TK_ROOT.destroy = lambda: [c.destroy() for c in _SHARED_TK_ROOT.winfo_children()]
        except Exception:
            _SHARED_TK_ROOT = None

    if _SHARED_TK_ROOT is not None:
        monkeypatch.setattr(tk, "Tk", lambda *args, **kwargs: _SHARED_TK_ROOT)
        for child in _SHARED_TK_ROOT.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

    yield

    if _SHARED_TK_ROOT is not None:
        for child in _SHARED_TK_ROOT.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
