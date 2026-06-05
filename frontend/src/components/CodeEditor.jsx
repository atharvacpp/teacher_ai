/**
 * CodeEditor.jsx — Monaco-based code editor with interactive xterm.js terminal.
 *
 * Features:
 *   • Language selector dropdown (Python, C, C++)
 *   • Monaco editor with dynamic syntax highlighting
 *   • "Run Code" button → opens WebSocket to /ws/execute
 *   • Real xterm.js terminal: stdout streams in real-time, user can type
 *     input directly (for input()/scanf/cin), stderr renders in ANSI red
 *
 * Props:
 *   initialCode  (string)  — pre-load code from the AI agent
 *   initialLang  (string)  — initial language ("python" | "c" | "cpp")
 */

import { useState, useRef, useEffect, useCallback } from "react";
import Editor from "@monaco-editor/react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { orchestrateDebug } from "../services/api";

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

// WebSocket URL — derive from current page origin for flexibility
const WS_URL = `ws://${window.location.hostname}:8000/ws/execute`;

export default function CodeEditor({ initialCode = "", initialLang = "python", activeVideo, onTakeQuiz }) {
  const getLanguageConfig = (id) => LANGUAGES.find((l) => l.id === id) || LANGUAGES[0];
  const transcriptLoaded = Boolean(activeVideo?.transcript);

  const [selectedLang, setSelectedLang] = useState(initialLang);
  const [codeByLanguage, setCodeByLanguage] = useState(() => {
    const defaultCodes = {};
    LANGUAGES.forEach(l => {
      defaultCodes[l.id] = l.defaultCode;
    });
    // Override the selected language with the initialCode if provided
    if (initialCode) {
      defaultCodes[initialLang] = initialCode;
    }
    return defaultCodes;
  });

  const code = codeByLanguage[selectedLang];
  const [isRunning, setIsRunning] = useState(false);
  const [exitStatus, setExitStatus] = useState(null); // "success" | "error" | null
  const [debugStatus, setDebugStatus] = useState(null); // null | "running" | "success" | "error"
  const [debugMessage, setDebugMessage] = useState("");

  const currentLang = getLanguageConfig(selectedLang);

  // Refs for xterm.js
  const terminalContainerRef = useRef(null);
  const terminalRef = useRef(null);    // Terminal instance
  const fitAddonRef = useRef(null);    // FitAddon instance
  const wsRef = useRef(null);          // WebSocket instance
  const onDataDisposableRef = useRef(null); // xterm onData listener
  const terminalInitialized = useRef(false);
  const inputBuffer = useRef("");      // Local line buffer for interactive input
  const terminalOutputRef = useRef(""); // Raw output from backend

  // Store code in a ref so the WebSocket callback always has the latest value
  const codeRef = useRef(code);
  const selectedLangRef = useRef(selectedLang);
  useEffect(() => { codeRef.current = code; }, [code]);
  useEffect(() => { selectedLangRef.current = selectedLang; }, [selectedLang]);

  // -----------------------------------------------------------------------
  // Initialize xterm.js on mount
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (terminalInitialized.current || !terminalContainerRef.current) return;

    const terminal = new Terminal({
      theme: {
        background: "#0d0b14",
        foreground: "#c8d6e5",
        cursor: "#8b5cf6",
        cursorAccent: "#0d0b14",
        selectionBackground: "rgba(139, 92, 246, 0.3)",
        black: "#0d0b14",
        red: "#ff6b6b",
        green: "#a8e6cf",
        yellow: "#ffa502",
        blue: "#8b5cf6",
        magenta: "#c084fc",
        cyan: "#67e8f9",
        white: "#c8d6e5",
        brightBlack: "#64748b",
        brightRed: "#f87171",
        brightGreen: "#34d399",
        brightYellow: "#fbbf24",
        brightBlue: "#a78bfa",
        brightMagenta: "#e879f9",
        brightCyan: "#22d3ee",
        brightWhite: "#f1f5f9",
      },
      fontFamily: "'Fira Code', 'Courier New', monospace",
      fontSize: 13,
      lineHeight: 1.4,
      cursorBlink: true,
      cursorStyle: "bar",
      scrollback: 5000,
      convertEol: false,
    });

    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(terminalContainerRef.current);

    // Initial fit
    try { fitAddon.fit(); } catch { /* ignore if container not visible yet */ }

    // Write welcome message
    terminal.writeln("\x1b[2m▍ Ready. Click 'Run Code' to execute.\x1b[0m");

    terminalRef.current = terminal;
    fitAddonRef.current = fitAddon;
    terminalInitialized.current = true;

    // Resize observer for responsive fitting
    const resizeObserver = new ResizeObserver(() => {
      try { fitAddon.fit(); } catch { /* ignore */ }
    });
    resizeObserver.observe(terminalContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (onDataDisposableRef.current) {
        onDataDisposableRef.current.dispose();
        onDataDisposableRef.current = null;
      }
      terminal.dispose();
      terminalInitialized.current = false;
    };
  }, []);


  // -----------------------------------------------------------------------
  // Language Switch
  // -----------------------------------------------------------------------

  const handleLanguageChange = (e) => {
    const newLang = e.target.value;
    setSelectedLang(newLang);
    setExitStatus(null);

    // Reset terminal
    if (terminalRef.current) {
      terminalRef.current.clear();
      terminalRef.current.writeln("\x1b[2m▍ Ready. Click 'Run Code' to execute.\x1b[0m");
      terminalOutputRef.current = "";
    }
  };

  // -----------------------------------------------------------------------
  // Code Execution via WebSocket
  // -----------------------------------------------------------------------

  const handleEditorChange = (value) => {
    setCodeByLanguage((prev) => ({
      ...prev,
      [selectedLang]: value || "",
    }));
  };

  const handleRunCode = useCallback(() => {
    const currentCode = codeRef.current;
    const lang = selectedLangRef.current;

    if (!currentCode.trim() || isRunning) return;

    const terminal = terminalRef.current;
    if (!terminal) return;

    // Close any existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Clean up any previous onData listener
    if (onDataDisposableRef.current) {
      onDataDisposableRef.current.dispose();
      onDataDisposableRef.current = null;
    }

    setIsRunning(true);
    setExitStatus(null);

    // Clear terminal and write run banner
    const langConfig = getLanguageConfig(lang);
    terminal.clear();
    terminalOutputRef.current = "";
    terminal.writeln(
      `\x1b[2m▶ Running ${langConfig.label} code in secure sandbox...\x1b[0m\r\n`
    );

    // Open WebSocket
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      // Send the code payload
      ws.send(JSON.stringify({
        code: currentCode,
        language: lang,
      }));

      // Now that WS is open, wire up terminal input → WS stdin with Local Echo
      onDataDisposableRef.current = terminal.onData((data) => {
        if (ws.readyState !== WebSocket.OPEN) return;

        if (data === '\r') {
          // Enter key
          terminal.write('\r\n');
          ws.send(inputBuffer.current + '\n');
          inputBuffer.current = "";
        } else if (data === '\u007F') {
          // Backspace key
          if (inputBuffer.current.length > 0) {
            inputBuffer.current = inputBuffer.current.slice(0, -1);
            terminal.write('\b \b');
          }
        } else {
          // Normal character
          inputBuffer.current += data;
          terminal.write(data);
        }
      });
    };

    ws.onmessage = (event) => {
      // Write incoming data (stdout/stderr with ANSI codes) to terminal
      terminal.write(event.data);
      terminalOutputRef.current += event.data;
    };

    ws.onclose = () => {
      setIsRunning(false);
      wsRef.current = null;

      // Clean up onData listener
      if (onDataDisposableRef.current) {
        onDataDisposableRef.current.dispose();
        onDataDisposableRef.current = null;
      }

      // Re-fit terminal after output
      try { fitAddonRef.current?.fit(); } catch { /* ignore */ }
    };

    ws.onerror = () => {
      terminal.writeln(
        "\r\n\x1b[31m[Connection Error] Could not connect to execution server.\x1b[0m"
      );
      terminal.writeln(
        "\x1b[2mMake sure the backend is running on port 8000.\x1b[0m"
      );
      setIsRunning(false);
      setExitStatus("error");
      wsRef.current = null;
    };
  }, [isRunning]);

  // Stop execution
  const handleStopCode = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsRunning(false);
    if (terminalRef.current) {
      terminalRef.current.writeln(
        "\r\n\x1b[33m⏹ Execution stopped by user.\x1b[0m"
      );
    }
  }, []);

  const handleMagicWand = useCallback(() => {
    const lang = selectedLangRef.current;
    const currentCode = codeRef.current;
    const terminalError = terminalOutputRef.current;

    setDebugStatus("running");
    setDebugMessage("✨ Connecting to E2B Sandbox...");

    orchestrateDebug(
      { code: currentCode, language: lang, terminal_error: terminalError },
      // onChunk
      (chunk) => {
        if (chunk.type === "log") {
          setDebugMessage(`✨ ${chunk.message}`);
        } else if (chunk.type === "success") {
          setDebugStatus("success");
          // Only update code if it actually changed
          if (chunk.code && chunk.code !== currentCode) {
            setDebugMessage("✅ Code fixed and applied to editor!");
            setCodeByLanguage((prev) => ({
              ...prev,
              [lang]: chunk.code,
            }));
          } else {
            setDebugMessage("✅ Code verified — no changes needed!");
          }
          // Write clean output to terminal (skip raw JSON blobs)
          if (terminalRef.current && chunk.output) {
            const output = chunk.output.trim();
            // Don't write raw E2B JSON structures to the terminal
            if (output && !output.startsWith("{") && !output.startsWith("[")) {
              terminalRef.current.writeln("\r\n\x1b[32m── DeepSeek Verified Output ──\x1b[0m");
              terminalRef.current.writeln(output);
            }
          }
          // Auto-clear status after 5s
          setTimeout(() => {
            setDebugStatus(null);
            setDebugMessage("");
          }, 5000);
        } else if (chunk.type === "error") {
          setDebugStatus("error");
          setDebugMessage(`❌ ${chunk.message}`);
          setTimeout(() => {
            setDebugStatus(null);
            setDebugMessage("");
          }, 8000);
        }
      },
      // onDone
      () => {
        if (debugStatus === "running") {
          setDebugStatus(null);
          setDebugMessage("");
        }
      },
      // onError
      (err) => {
        setDebugStatus("error");
        setDebugMessage(`❌ Failed: ${err.message}`);
        setTimeout(() => {
          setDebugStatus(null);
          setDebugMessage("");
        }, 8000);
      }
    );
  }, [debugStatus]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

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

          <div className="editor-header__actions">
            {/* Stop Button (visible while running) */}
            {isRunning && (
              <button
                id="stop-code-button"
                className="stop-exec-button"
                onClick={handleStopCode}
              >
                <svg width="12" height="12" viewBox="0 0 18 18" fill="currentColor">
                  <rect x="3" y="3" width="12" height="12" rx="2" />
                </svg>
                Stop
              </button>
            )}

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

            {/* 🎯 Take Quiz Button */}
            <button
              id="take-quiz-button"
              className="run-button"
              onClick={onTakeQuiz}
              disabled={!transcriptLoaded}
              title={transcriptLoaded ? "Enter Focus Mode — AI-generated quiz from this video" : "Waiting for transcript to load..."}
            >
              🎯 Take Quiz
            </button>

            {/* ✨ Magic Wand Debugger */}
            <button
              id="magic-wand-button"
              className="run-button"
              style={{ backgroundColor: debugStatus === "running" ? "#6d28d9" : "#8b5cf6" }}
              onClick={handleMagicWand}
              disabled={isRunning || debugStatus === "running"}
              title="Debug this code automatically using DeepSeek"
            >
              {debugStatus === "running" ? (
                <>
                  <span className="dot-pulse" style={{ width: "6px", height: "6px", backgroundColor: "#fff", marginRight: "6px" }} />
                  Fixing...
                </>
              ) : (
                "✨ Debug with AI"
              )}
            </button>
          </div>
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

      {/* Bottom Pane: Xterm.js Terminal */}
      <div className="terminal-pane">
        <div className="terminal-header">
          <span className="terminal-title">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ marginRight: "6px", verticalAlign: "-1px" }}
            >
              <polyline points="4 17 10 11 4 5" />
              <line x1="12" y1="19" x2="20" y2="19" />
            </svg>
            Interactive Terminal
          </span>
          {exitStatus && (
            <span
              className={`terminal-badge ${
                exitStatus === "error" ? "badge-error" : "badge-success"
              }`}
            >
              {exitStatus === "error" ? "Failed" : "Success"}
            </span>
          )}
        </div>
        {debugMessage && (
          <div style={{
            padding: "6px 14px",
            fontSize: "12px",
            fontFamily: "'Fira Code', monospace",
            background: debugStatus === "error" ? "rgba(239,68,68,0.15)" : debugStatus === "success" ? "rgba(34,197,94,0.15)" : "rgba(139,92,246,0.15)",
            color: debugStatus === "error" ? "#f87171" : debugStatus === "success" ? "#4ade80" : "#c4b5fd",
            borderBottom: "1px solid rgba(139,92,246,0.2)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}>
            {debugStatus === "running" && (
              <span style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#8b5cf6", animation: "pulse 1.5s ease-in-out infinite" }} />
            )}
            {debugMessage}
          </div>
        )}
        <div className="xterm-container" ref={terminalContainerRef} />
      </div>
    </div>
  );
}
