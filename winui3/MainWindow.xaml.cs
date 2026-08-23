using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Text.Json;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;

namespace SmartCr.WinUI;

public sealed partial class MainWindow : Window
{
    private readonly string _projectRoot;
    private Process? _syncProcess;

    public MainWindow()
    {
        InitializeComponent();
        Closed += (_, _) => StopSyncProcess();
        _projectRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        RefreshData();
    }

    private void RefreshButton_Click(object sender, RoutedEventArgs e) => RefreshData();

    private void RefreshData()
    {
        var archivePath = Path.Combine(_projectRoot, "data", "data.zip");
        try
        {
            using var archive = ZipFile.OpenRead(archivePath);
            using var stream = archive.GetEntry("data.json")?.Open() ?? throw new InvalidDataException();
            using var document = JsonDocument.Parse(stream);
            VersionText.Text = document.RootElement.GetProperty("version").ToString();
            LogText.Text = $"{DateTime.Now:T}  已读取本地课程数据。";
        }
        catch (Exception)
        {
            VersionText.Text = "不可用";
            LogText.Text = "未找到有效的 data/data.zip，请先准备课程数据。";
        }
    }

    private void SyncButton_Click(object sender, RoutedEventArgs e)
    {
        if (_syncProcess is { HasExited: false })
        {
            StopSyncProcess();
            ServiceText.Text = "未启动";
            SyncButton.Content = "启动同步";
            StatusText.Text = "同步服务已停止";
            return;
        }

        var python = FindPython();
        if (python is null)
        {
            StatusText.Text = "未找到 Python 解释器";
            LogText.Text = "请先创建虚拟环境，或将 python 加入 PATH。";
            return;
        }

        _syncProcess = Process.Start(new ProcessStartInfo
        {
            FileName = python,
            Arguments = "main.py",
            WorkingDirectory = _projectRoot,
            UseShellExecute = false,
            CreateNoWindow = true
        });
        ServiceText.Text = "运行中";
        SyncButton.Content = "停止同步";
        StatusText.Text = "正在发现局域网节点并检查更新";
        LogText.Text = $"{DateTime.Now:T}  同步服务已启动。";
    }

    private void StopSyncProcess()
    {
        if (_syncProcess is null)
        {
            return;
        }

        if (!_syncProcess.HasExited)
        {
            _syncProcess.Kill(entireProcessTree: true);
        }

        _syncProcess.Dispose();
        _syncProcess = null;
    }

    private string? FindPython()
    {
        var virtualEnvPython = Path.Combine(_projectRoot, ".venv", "Scripts", "python.exe");
        return File.Exists(virtualEnvPython) ? virtualEnvPython : "python";
    }
}