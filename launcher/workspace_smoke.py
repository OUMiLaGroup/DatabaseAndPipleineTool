"""Opt-in real WebView2 smoke check; uses synthetic files and the saved CVAT login."""
import json
from pathlib import Path
import tempfile
import time


def execute(host, kind, script):
    tasks = []
    host.ui(lambda: tasks.append(host.remotes[kind].CoreWebView2.ExecuteScriptAsync(script)))
    wait_for(lambda: tasks[0].IsCompleted, 'Browser script did not complete', seconds=15)
    return json.loads(str(tasks[0].Result))


def wait_for(probe, description, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(.2)
    raise AssertionError(description)


def run_smoke(host):
    from workspace import URLS
    print('Checking browser initialization...', flush=True)
    for kind in URLS:
        assert host.remote_initialized[kind].wait(30), f"{kind} did not initialize"
    assert len(host.tabs.TabPages) == 3, "Workspace should have three native tabs"
    def check_toolbar_layout():
        for kind in URLS:
            host.tabs.SelectedTab = host.pages[kind]
            layout, toolbar = host.browser_layouts[kind]
            layout.PerformLayout()
            assert host.remotes[kind].Top >= toolbar.Bottom, f'{kind} toolbar overlaps browser'
            assert toolbar.Height >= 40, f'{kind} toolbar must reserve about 40 pixels'
            for button in list(toolbar.Controls)[:3]:
                assert button.Image is not None and button.Text == '', 'Navigation buttons should use icons'
                assert button.AccessibleName, 'Icon buttons need accessible names'
        host.tabs.SelectedTab = host.pages['setup']
    host.ui(check_toolbar_layout)
    print('Checking setup bridge...', flush=True)
    setup = wait_for(lambda: host.window.evaluate_js("Boolean(window.pywebview && window.pywebview.api && window.pywebview.api.state)"), "Setup bridge unavailable")
    assert setup
    wait_for(lambda: host.window.evaluate_js("document.getElementById('existing').getAttribute('aria-pressed') === 'true'"), 'Saved account mode did not load')
    assert host.window.evaluate_js("document.getElementById('new-account').hidden"), 'Existing Account should hide input fields and help links'
    host.window.evaluate_js("document.getElementById('new').click()")
    assert host.window.evaluate_js("!document.getElementById('new-account').hidden"), 'New Account should show input fields'
    host.window.evaluate_js("document.getElementById('existing').click()")
    assert host.window.evaluate_js("document.getElementById('new-account').hidden"), 'Toggle should restore Existing Account mode'
    print('Running existing startup workflow...', flush=True)
    status = host.installer.start("existing", {})
    assert status.get("ok"), status.get("error")
    wait_for(lambda: not host.installer.running, "Startup did not finish", seconds=360)
    assert host.installer.code == 0, "Startup checks failed"
    wait_for(lambda: len(host.loaded) == 2, "Dashboards did not load")
    print('Checking dashboard rendering and bridge isolation...', flush=True)
    for kind in URLS:
        host.select_tab(kind)
        try:
            wait_for(lambda k=kind: execute(host, k, f"location.origin === {json.dumps(URLS[k])} && document.readyState === 'complete' && document.body.innerText.length > 20"), f"{kind} did not render")
        except AssertionError:
            diagnostic = execute(host, kind, "({origin:location.origin,path:location.pathname,title:document.title,state:document.readyState,children:document.body.children.length,textLength:document.body.innerText.length})")
            raise AssertionError(f'{kind} did not render: {diagnostic}')
        assert execute(host, kind, "typeof window.pywebview === 'undefined'"), "Dashboard must not receive privileged setup bridge"

    # Exercise the actual local CVAT session without printing credentials/tokens.
    saved = host.installer.saved
    print('Checking CVAT authentication...', flush=True)
    credentials = json.dumps({"username": saved["CVAT_EMAIL"], "password": saved["CVAT_PASSWORD"]})
    execute(host, "cvat", """
      window.__milaAuth = null;
      (async () => {
        try {
          let response = await fetch('/api/users/self', {credentials:'include'});
          if (!response.ok) {
            const csrf = document.cookie.split('; ').find(v=>v.startsWith('csrftoken='));
            const headers = {'Content-Type':'application/json'};
            if(csrf) headers['X-CSRFToken'] = decodeURIComponent(csrf.split('=')[1]);
            response = await fetch('/api/auth/login', {method:'POST', credentials:'include', headers,
                                                     body:JSON.stringify(CREDENTIALS)});
          }
          const check = await fetch('/api/users/self', {credentials:'include'});
          window.__milaAuth = check.ok;
        } catch(e) { window.__milaAuth = false; }
      })();
    """.replace("CREDENTIALS", credentials))
    wait_for(lambda: execute(host, "cvat", "window.__milaAuth !== null"), "CVAT authentication timed out")
    assert execute(host, "cvat", "window.__milaAuth === true"), "CVAT authentication failed"
    print('CVAT authentication passed; checking tasks page...', flush=True)
    host.ui(lambda: host.remotes["cvat"].CoreWebView2.Navigate(URLS["cvat"] + "/tasks"))
    wait_for(lambda: execute(host, "cvat", "location.pathname === '/tasks' && document.body.innerText.includes('Tasks')"), "CVAT tasks page did not render")

    # MiLa's Open in CVAT link should select the existing tab, not open a browser.
    execute(host, "mila", "window.open('http://localhost:8080/tasks', '_blank'); true")
    wait_for(lambda: host.tabs.SelectedTab == host.pages["cvat"], "CVAT popup did not select its tab")

    # WebView2's actual file-input/download mechanisms, using disposable files.
    print('Checking embedded file input and downloads...', flush=True)
    with tempfile.TemporaryDirectory(prefix="mila-webview-files-") as folder:
        folder = Path(folder)
        upload = folder / "upload-check.txt"
        upload.write_text("synthetic upload content", encoding="utf-8")
        download = folder / "download-check.txt"
        host.ui(lambda: host.remotes["mila"].CoreWebView2.NavigateToString(
            '<html><body><input id="file" type="file"><button id="download">Download</button>'
            '<script>document.getElementById("download").onclick=()=>{'
            'const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["synthetic download content"]));'
            'a.download="download-check.txt";a.click();};</script></body></html>'))
        wait_for(lambda: execute(host, "mila", "Boolean(document.getElementById('file'))"), "Transfer fixture did not load")
        cores = []
        host.ui(lambda: cores.append(host.remotes["mila"].CoreWebView2))
        core = cores[0]
        tasks = []
        host.ui(lambda: tasks.append(core.CallDevToolsProtocolMethodAsync("DOM.getDocument", "{}")))
        wait_for(lambda: tasks[0].IsCompleted, 'DOM document request did not complete', seconds=15)
        root = json.loads(str(tasks[0].Result))["root"]["nodeId"]
        tasks = []
        host.ui(lambda: tasks.append(core.CallDevToolsProtocolMethodAsync("DOM.querySelector", json.dumps({"nodeId":root, "selector":"#file"}))))
        wait_for(lambda: tasks[0].IsCompleted, 'DOM selector request did not complete', seconds=15)
        node = json.loads(str(tasks[0].Result))["nodeId"]
        tasks = []
        host.ui(lambda: tasks.append(core.CallDevToolsProtocolMethodAsync("DOM.setFileInputFiles", json.dumps({"nodeId":node, "files":[str(upload)]}))))
        wait_for(lambda: tasks[0].IsCompleted, 'File input request did not complete', seconds=15)
        assert execute(host, "mila", "document.getElementById('file').files[0].name") == upload.name
        host._smoke_download_path = str(download)
        try:
            execute(host, "mila", "document.getElementById('download').click(); true")
            wait_for(lambda: download.exists() and download.read_text(encoding="utf-8") == "synthetic download content", "Embedded download failed")
        finally:
            host._smoke_download_path = None
        host.ui(lambda: core.Navigate(URLS["mila"]))
    print("PASS: native file input and blob download (synthetic files).")
