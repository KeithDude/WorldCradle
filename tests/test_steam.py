import os

import steam


def _lib(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    return path


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(steam, "REDIST_DIR", str(tmp_path / "redist"))
    monkeypatch.setattr(steam, "PRIVATE_DIR", str(tmp_path / "steamcmd"))
    fetched = []
    monkeypatch.setattr(steam, "app_update", lambda app, d, **kw: fetched.append(app) or
                        [_lib(os.path.join(d, f"linux{b}", "steamclient.so")) for b in (32, 64)])
    return fetched


def test_links_both_client_libraries_fetching_the_redist_once(tmp_path, monkeypatch):
    fetched = _setup(tmp_path, monkeypatch)
    _lib(str(tmp_path / "steamcmd/linux32/steamclient.so"))   # steamcmd only carries the 32-bit one
    steam.link_client_libs()
    assert fetched == [steam.REDIST_APP]
    assert os.readlink(tmp_path / ".steam/sdk64/steamclient.so") == str(tmp_path / "redist/linux64/steamclient.so")
    assert os.readlink(tmp_path / ".steam/sdk32/steamclient.so") == str(tmp_path / "redist/linux32/steamclient.so")
    steam.link_client_libs()            # all there now: nothing more to do
    assert fetched == [steam.REDIST_APP]


def test_leaves_existing_libraries_alone_and_replaces_dangling_links(tmp_path, monkeypatch):
    fetched = _setup(tmp_path, monkeypatch)
    own = _lib(str(tmp_path / ".steam/sdk64/steamclient.so"))   # the owner's own setup
    os.makedirs(tmp_path / ".steam/sdk32")
    os.symlink(tmp_path / "gone/steamclient.so", tmp_path / ".steam/sdk32/steamclient.so")
    _lib(str(tmp_path / "steamcmd/linux32/steamclient.so"))
    steam.link_client_libs()
    assert fetched == []
    assert os.path.isfile(own) and not os.path.islink(own)
    assert os.readlink(tmp_path / ".steam/sdk32/steamclient.so") == str(tmp_path / "steamcmd/linux32/steamclient.so")
