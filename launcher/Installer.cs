using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Installer {
    static string Hash(byte[] bytes) { using (var sha = SHA256.Create()) { return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", ""); } }
    static void Extract(string destination) {
        string root = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string marker = Path.Combine(root, ".mila-release-manifest.json");
        var serializer = new JavaScriptSerializer();
        var old = File.Exists(marker) ? serializer.Deserialize<Dictionary<string,string>>(File.ReadAllText(marker)) : new Dictionary<string,string>();
        if (Directory.Exists(root) && Directory.GetFileSystemEntries(root).Length > 0 && !File.Exists(marker))
            throw new IOException("The installation folder already contains unmanaged files. Choose an empty folder.");
        var files = new Dictionary<string,byte[]>();
        var manifest = new Dictionary<string,string>();
        using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("MiLa.Project.zip"))
        using (var zip = new ZipArchive(stream, ZipArchiveMode.Read)) {
            foreach (var entry in zip.Entries) {
                string name = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                string target = Path.GetFullPath(Path.Combine(root, name));
                if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase) || name.Contains(":") || Path.IsPathRooted(name))
                    throw new IOException("Invalid archive path.");
                // Reject junctions/symlinks before writing any existing installation path.
                for (string part = Path.GetDirectoryName(target); part != null && part.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase); part = Path.GetDirectoryName(part))
                    if (Directory.Exists(part) && (File.GetAttributes(part) & FileAttributes.ReparsePoint) != 0) throw new IOException("Installation folder contains a linked directory.");
                byte[] bytes;
                using (var input = entry.Open()) using (var output = new MemoryStream()) { input.CopyTo(output); bytes = output.ToArray(); }
                string hash = Hash(bytes);
                if (File.Exists(target)) {
                    if ((File.GetAttributes(target) & FileAttributes.ReparsePoint) != 0) throw new IOException("Installation contains a linked file.");
                    string current = Hash(File.ReadAllBytes(target));
                    string previous;
                    if (current != hash && (!old.TryGetValue(name, out previous) || current != previous))
                        throw new IOException("A project file was edited locally: " + name + ". Back up your changes before updating.");
                }
                files.Add(name, bytes); manifest.Add(name, hash);
            }
        }
        Directory.CreateDirectory(root);
        foreach (var file in files) {
            string target = Path.Combine(root, file.Key);
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            File.WriteAllBytes(target, file.Value);
        }
        File.WriteAllText(marker, serializer.Serialize(manifest));
        Directory.CreateDirectory(Path.Combine(root, "minio"));
    }
    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MiLa", "Project");
        bool extractOnly = args.Length == 2 && args[0] == "--extract-only";
        if (extractOnly) root = args[1];
        try {
            Extract(root);
            if (extractOnly) return 0;
            var form = new Form { Text = "Preparing MiLa", Width = 550, Height = 180, StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false };
            var label = new Label { Left = 20, Top = 20, Width = 500, Height = 55, Text = "Preparing the launcher. Missing Python and browser components will download automatically. Please keep this window open." };
            form.Controls.Add(label);
            form.Controls.Add(new ProgressBar { Left = 20, Top = 90, Width = 495, Style = ProgressBarStyle.Marquee });
            string ready = Path.Combine(Path.GetTempPath(), "mila-ready-" + Guid.NewGuid().ToString("N"));
            var start = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe"));
            start.Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File \"" + Path.Combine(root, "launcher", "Setup-MiLa.ps1") + "\" -BootstrapReadyFile \"" + ready + "\"";
            start.WorkingDirectory = root; start.UseShellExecute = false; start.CreateNoWindow = true;
            start.RedirectStandardOutput = true; start.RedirectStandardError = true;
            var errors = new System.Text.StringBuilder();
            var process = new Process { StartInfo = start };
            process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (!String.IsNullOrEmpty(e.Data) && form.IsHandleCreated && !form.IsDisposed) { try { form.BeginInvoke((Action)delegate { label.Text = e.Data; }); } catch (InvalidOperationException) {} } };
            process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) lock(errors) errors.AppendLine(e.Data); };
            process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine();
            bool readySeen = false;
            var timer = new System.Windows.Forms.Timer { Interval = 500 };
            timer.Tick += delegate {
                if (File.Exists(ready)) { readySeen = true; File.Delete(ready); timer.Stop(); form.Close(); }
                else if (process.HasExited) { process.WaitForExit(); timer.Stop(); string details; lock(errors) details = errors.ToString(); MessageBox.Show("Launcher preparation stopped. Reopen the installer to retry.\n\n" + details, "MiLa setup"); form.Close(); }
            };
            form.FormClosing += delegate(object sender, FormClosingEventArgs e) { if (!readySeen && !process.HasExited) e.Cancel = true; };
            timer.Start(); Application.Run(form);
            // Leave the Python GUI and its PowerShell parent running after the splash closes.
            return readySeen ? 0 : 1;
        } catch (Exception e) { if (!extractOnly) MessageBox.Show(e.Message, "MiLa installation"); return 1; }
    }
}
