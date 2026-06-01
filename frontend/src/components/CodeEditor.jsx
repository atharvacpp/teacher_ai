/**
 * CodeEditor.jsx — Monaco-based code editor with multi-language support.
 *
 * Features:
 *   • Language selector dropdown (Python, C, C++)
 *   • Monaco editor with dynamic syntax highlighting
 *   • "Run Code" button → POST /execute-code with { code, language }
 *   • Terminal pane showing execution output + success/error badges
 *
 * Props:
 *   initialCode  (string)  — pre-load code from the AI agent
 *   initialLang  (string)  — initial language ("python" | "c" | "cpp")
 */

import React, { useState } from "react";
import Editor from "@monaco-editor/react";
import { executeCode } from "../services/api";

// ---------------------------------------------------------------------------
// Language Configuration
// ---------------------------------------------------------------------------

const LANGUAGES = [
  {
    id: "python",
    label: "Python",
    icon: "🐍",
    monacoId: "python",
    defaultCode: '# Write your Python code here...\n\nprint("Hello from ExplainAI Sandbox!")\n',
  },
  {
    id: "c",
    label: "C",
    icon: "⚙️",
    monacoId: "c",
    defaultCode:
      '#include <stdio.h>\n\nint main() {\n    printf("Hello from ExplainAI Sandbox!\\n");\n    return 0;\n}\n',
  },
  {
    id: "cpp",
    label: "C++",
    icon: "⚡",
    monacoId: "cpp",
    defaultCode:
      '#include <iostream>\n\nint main() {\n    std::cout << "Hello from ExplainAI Sandbox!" << std::endl;\n    return 0;\n}\n',
  },
];

export default function CodeEditor({ initialCode = "", initialLang = "python" }) {
  const getLanguageConfig = (id) => LANGUAGES.find((l) => l.id === id) || LANGUAGES[0];

  const [selectedLang, setSelectedLang] = useState(initialLang);
  const [code, setCode] = useState(
    initialCode || getLanguageConfig(initialLang).defaultCode
  );
  const [logs, setLogs] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [executionDetails, setExecutionDetails] = useState(null);

  const currentLang = getLanguageConfig(selectedLang);

  // -----------------------------------------------------------------------
  // Language Switch
  // -----------------------------------------------------------------------

  const handleLanguageChange = (e) => {
    const newLang = e.target.value;
    const langConfig = getLanguageConfig(newLang);
    setSelectedLang(newLang);
    // Reset editor to default code for the new language
    setCode(langConfig.defaultCode);
    // Clear terminal
    setLogs("");
    setExecutionDetails(null);
  };

  // -----------------------------------------------------------------------
  // Code Execution
  // -----------------------------------------------------------------------

  const handleEditorChange = (value) => {
    setCode(value);
  };

  const handleRunCode = async () => {
    if (!code.trim() || isRunning) return;

    setIsRunning(true);
    setLogs(`Running ${currentLang.label} code in secure sandbox...\n`);
    setExecutionDetails(null);

    try {
      const response = await executeCode(code, selectedLang);

      let logOutput = "";
      if (response.has_error) {
        logOutput += `[Error] Execution failed after ${response.attempts} attempt(s).\n\n`;
      } else {
        logOutput += `[Success] Execution completed in ${response.attempts} attempt(s).\n\n`;
      }

      logOutput += response.output || "(no output)";

      if (response.fixed_code && response.has_error === false) {
        logOutput += `\n\n[Debugger] The AI debugger automatically fixed the code to make it run.`;
      }

      setLogs(logOutput);
      setExecutionDetails(response);
    } catch (error) {
      setLogs(`[System Error] ${error.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="code-editor-container">
      {/* Top Pane: Monaco Editor */}
      <div className="editor-pane">
        <div className="editor-header">
          {/* Language Selector */}
          <div className="lang-selector-wrapper">
            <select
              id="language-selector"
              className="lang-selector"
              value={selectedLang}
              onChange={handleLanguageChange}
              disabled={isRunning}
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.id} value={lang.id}>
                  {lang.icon} {lang.label}
                </option>
              ))}
            </select>
          </div>

          {/* Run Button */}
          <button
            id="run-code-button"
            className="run-button"
            onClick={handleRunCode}
            disabled={isRunning}
          >
            {isRunning ? (
              <>
                <span
                  className="dot-pulse"
                  style={{
                    width: "6px",
                    height: "6px",
                    backgroundColor: "#fff",
                    marginRight: "6px",
                  }}
                />
                Running...
              </>
            ) : (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  style={{ marginRight: "6px" }}
                >
                  <path d="M8 5v14l11-7z" />
                </svg>
                Run Code
              </>
            )}
          </button>
        </div>

        <div className="editor-wrapper">
          <Editor
            height="100%"
            language={currentLang.monacoId}
            theme="vs-dark"
            value={code}
            onChange={handleEditorChange}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              fontFamily: "'Fira Code', 'Courier New', monospace",
              wordWrap: "on",
              padding: { top: 16, bottom: 16 },
              scrollBeyondLastLine: false,
              smoothScrolling: true,
            }}
          />
        </div>
      </div>

      {/* Bottom Pane: Terminal */}
      <div className="terminal-pane">
        <div className="terminal-header">
          <span className="terminal-title">Terminal Output</span>
          {executionDetails && (
            <span
              className={`terminal-badge ${
                executionDetails.has_error ? "badge-error" : "badge-success"
              }`}
            >
              {executionDetails.has_error ? "Failed" : "Success"}
            </span>
          )}
        </div>
        <div className="terminal-window">
          <pre className="terminal-logs">
            {logs || "Ready. Select a language and click 'Run Code' to execute."}
          </pre>
        </div>
      </div>
    </div>
  );
}
