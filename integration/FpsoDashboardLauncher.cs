using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace FpsoDashboardIntegration
{
    /// <summary>
    /// C# 해석 프로그램에서 SQLite DB 저장이 끝난 뒤 Python Streamlit dashboard를 실행하는 헬퍼입니다.
    /// 기존 C# 해석 코드의 "마지막 단계"에서 LaunchDashboard(...)만 호출하면 됩니다.
    /// </summary>
    public static class FpsoDashboardLauncher
    {
        /// <summary>
        /// 해석 결과 DB를 dashboard에 연결해서 실행합니다.
        /// </summary>
        /// <param name="dbFilePath">C# 해석 코드가 생성한 SQLite *.db 파일 경로입니다.</param>
        /// <param name="dashboardDirectory">app.py가 있는 dashboard 프로젝트 폴더입니다.</param>
        /// <param name="port">Streamlit을 띄울 포트입니다. 기본값은 8508입니다.</param>
        /// <param name="pythonExe">
        /// Python 실행 파일 경로입니다.
        /// 비워 두면 dashboard 폴더의 .venv\Scripts\python.exe를 먼저 찾고,
        /// 없으면 Windows Python Launcher(py -3.13)를 사용합니다.
        /// </param>
        /// <returns>새로 실행한 Streamlit 프로세스입니다. 이미 포트가 열려 있으면 null을 반환합니다.</returns>
        public static Process LaunchDashboard(
            string dbFilePath,
            string dashboardDirectory,
            int port = 8508,
            string pythonExe = null)
        {
            string fullDbPath = Path.GetFullPath(dbFilePath);
            string fullDashboardDirectory = Path.GetFullPath(dashboardDirectory);
            string appPath = Path.Combine(fullDashboardDirectory, "app.py");

            if (!File.Exists(fullDbPath))
            {
                throw new FileNotFoundException("Dashboard에 연결할 SQLite DB 파일을 찾지 못했습니다.", fullDbPath);
            }

            if (!File.Exists(appPath))
            {
                throw new FileNotFoundException("Dashboard app.py 파일을 찾지 못했습니다.", appPath);
            }

            WaitUntilFileReady(fullDbPath, TimeSpan.FromSeconds(10));

            string url = BuildDashboardUrl(port, fullDbPath);

            // 이미 dashboard가 떠 있으면 새 프로세스를 만들지 않고 브라우저만 해당 DB query로 엽니다.
            // app.py가 ?db=... query를 읽도록 되어 있어, 실행 중인 dashboard에서도 DB 경로를 바꿀 수 있습니다.
            if (IsPortOpen("127.0.0.1", port, TimeSpan.FromMilliseconds(300)))
            {
                OpenBrowser(url);
                return null;
            }

            string resolvedPythonExe = ResolvePythonExecutable(fullDashboardDirectory, pythonExe);
            ProcessStartInfo startInfo = BuildStreamlitStartInfo(
                resolvedPythonExe,
                fullDashboardDirectory,
                fullDbPath,
                port);

            Process process = Process.Start(startInfo);
            if (process == null)
            {
                throw new InvalidOperationException("Streamlit dashboard 프로세스를 시작하지 못했습니다.");
            }

            // Streamlit이 포트를 열 시간을 조금 준 뒤 브라우저를 엽니다.
            WaitUntilPortOpen("127.0.0.1", port, TimeSpan.FromSeconds(20));
            OpenBrowser(url);

            return process;
        }

        /// <summary>
        /// 프로젝트 .venv가 있으면 그것을 우선 사용하고, 없으면 py -3.13을 사용합니다.
        /// </summary>
        private static string ResolvePythonExecutable(string dashboardDirectory, string pythonExe)
        {
            if (!string.IsNullOrWhiteSpace(pythonExe))
            {
                return pythonExe;
            }

            string venvPython = Path.Combine(dashboardDirectory, ".venv", "Scripts", "python.exe");
            if (File.Exists(venvPython))
            {
                return venvPython;
            }

            return "py";
        }

        /// <summary>
        /// Streamlit 실행에 필요한 ProcessStartInfo를 만듭니다.
        /// </summary>
        private static ProcessStartInfo BuildStreamlitStartInfo(
            string pythonExe,
            string dashboardDirectory,
            string dbFilePath,
            int port)
        {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = pythonExe;
            startInfo.WorkingDirectory = dashboardDirectory;
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            startInfo.Arguments = BuildStreamlitArguments(pythonExe, dbFilePath, port);

            // app.py는 CLI 인자와 환경변수를 모두 지원합니다.
            // 일부 실행 환경에서 CLI 인자를 보기 어렵더라도 환경변수로 한 번 더 전달됩니다.
            startInfo.EnvironmentVariables["FPSO_DASHBOARD_DB"] = dbFilePath;

            return startInfo;
        }

        /// <summary>
        /// python.exe 뒤에 붙일 Streamlit 실행 인자를 한 줄의 문자열로 만듭니다.
        /// ProcessStartInfo.ArgumentList를 쓰지 않아서 .NET Framework 프로젝트에도 붙이기 쉽습니다.
        /// </summary>
        private static string BuildStreamlitArguments(string pythonExe, string dbFilePath, int port)
        {
            StringBuilder arguments = new StringBuilder();

            // py launcher를 쓰는 경우 "py -3.13 -m streamlit ..." 형태가 되어야 합니다.
            if (Path.GetFileNameWithoutExtension(pythonExe).Equals("py", StringComparison.OrdinalIgnoreCase))
            {
                AddArgument(arguments, "-3.13");
            }

            AddArgument(arguments, "-m");
            AddArgument(arguments, "streamlit");
            AddArgument(arguments, "run");
            AddArgument(arguments, "app.py");
            AddArgument(arguments, "--server.port");
            AddArgument(arguments, port.ToString(CultureInfo.InvariantCulture));
            AddArgument(arguments, "--server.headless");
            AddArgument(arguments, "true");
            AddArgument(arguments, "--browser.gatherUsageStats");
            AddArgument(arguments, "false");

            // "--" 뒤의 인자는 Streamlit이 아니라 app.py로 전달됩니다.
            AddArgument(arguments, "--");
            AddArgument(arguments, "--db");
            AddArgument(arguments, dbFilePath);

            return arguments.ToString();
        }

        /// <summary>
        /// 공백이 있는 Windows 경로도 안전하게 전달되도록 인자를 추가합니다.
        /// </summary>
        private static void AddArgument(StringBuilder builder, string argument)
        {
            if (builder.Length > 0)
            {
                builder.Append(' ');
            }

            builder.Append(QuoteArgument(argument));
        }

        /// <summary>
        /// ProcessStartInfo.Arguments에 넣을 단일 인자를 Windows 규칙에 맞게 감쌉니다.
        /// 예: C:\My Project\result.db -> "C:\My Project\result.db"
        /// </summary>
        private static string QuoteArgument(string argument)
        {
            if (argument == null)
            {
                return "\"\"";
            }

            if (argument.Length > 0 && argument.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0)
            {
                return argument;
            }

            StringBuilder quoted = new StringBuilder();
            int backslashCount = 0;

            quoted.Append('"');
            foreach (char currentChar in argument)
            {
                if (currentChar == '\\')
                {
                    backslashCount++;
                    continue;
                }

                if (currentChar == '"')
                {
                    quoted.Append('\\', backslashCount * 2 + 1);
                    quoted.Append('"');
                    backslashCount = 0;
                    continue;
                }

                quoted.Append('\\', backslashCount);
                quoted.Append(currentChar);
                backslashCount = 0;
            }

            quoted.Append('\\', backslashCount * 2);
            quoted.Append('"');

            return quoted.ToString();
        }

        /// <summary>
        /// DB 파일이 아직 쓰이는 중이면 잠시 기다립니다.
        /// </summary>
        private static void WaitUntilFileReady(string filePath, TimeSpan timeout)
        {
            DateTime deadline = DateTime.UtcNow.Add(timeout);

            while (DateTime.UtcNow < deadline)
            {
                try
                {
                    using (FileStream stream = new FileStream(
                        filePath,
                        FileMode.Open,
                        FileAccess.Read,
                        FileShare.ReadWrite))
                    {
                        if (stream.Length > 0)
                        {
                            return;
                        }
                    }
                }
                catch (IOException)
                {
                    // C# 해석 코드나 SQLite writer가 아직 파일을 붙잡고 있을 수 있습니다.
                }
                catch (UnauthorizedAccessException)
                {
                    // 바이러스 검사나 동기화 프로그램이 순간적으로 접근을 막는 경우를 대비합니다.
                }

                Thread.Sleep(200);
            }

            throw new TimeoutException("DB 파일이 준비될 때까지 기다렸지만 시간 초과되었습니다: " + filePath);
        }

        /// <summary>
        /// 지정한 포트가 열릴 때까지 기다립니다.
        /// </summary>
        private static void WaitUntilPortOpen(string host, int port, TimeSpan timeout)
        {
            DateTime deadline = DateTime.UtcNow.Add(timeout);

            while (DateTime.UtcNow < deadline)
            {
                if (IsPortOpen(host, port, TimeSpan.FromMilliseconds(300)))
                {
                    return;
                }

                Thread.Sleep(300);
            }

            throw new TimeoutException(
                "Dashboard 포트가 열리지 않았습니다: " + host + ":" + port.ToString(CultureInfo.InvariantCulture));
        }

        /// <summary>
        /// localhost 포트가 이미 열려 있는지 확인합니다.
        /// </summary>
        private static bool IsPortOpen(string host, int port, TimeSpan timeout)
        {
            try
            {
                using (TcpClient client = new TcpClient())
                {
                    IAsyncResult result = client.BeginConnect(host, port, null, null);
                    bool connected = result.AsyncWaitHandle.WaitOne(timeout);

                    if (!connected)
                    {
                        return false;
                    }

                    client.EndConnect(result);
                    return true;
                }
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// 기본 브라우저로 dashboard URL을 엽니다.
        /// </summary>
        private static void OpenBrowser(string url)
        {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = url;
            startInfo.UseShellExecute = true;

            Process.Start(startInfo);
        }

        /// <summary>
        /// DB 경로를 query string으로 포함한 dashboard URL을 만듭니다.
        /// </summary>
        private static string BuildDashboardUrl(int port, string dbFilePath)
        {
            string encodedDbPath = Uri.EscapeDataString(dbFilePath);
            return "http://127.0.0.1:" + port.ToString(CultureInfo.InvariantCulture) + "/?db=" + encodedDbPath;
        }
    }
}
