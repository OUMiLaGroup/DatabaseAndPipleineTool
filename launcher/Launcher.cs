using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
internal static class Launcher {
    [STAThread] static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(root, "launcher", "Setup-MiLa.ps1");
        if (!File.Exists(script)) {
            MessageBox.Show("Keep MiLa-Launcher.exe inside the complete MiLa project folder.", "MiLa");
            return;
        }
        var start = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe"));
        start.Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File \"" + script + "\"";
        start.WorkingDirectory = root;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        try { Process.Start(start); }
        catch (Exception e) { MessageBox.Show(e.Message, "Unable to open MiLa"); }
    }
}
