Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "C:\path\to\mokuro-gui"
shell.Run "cmd /c .venv\Scripts\activate && python main.py", 0