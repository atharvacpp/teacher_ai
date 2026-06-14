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
    defaultCode: '# Write your Python code here...\n\nprint("Hello from Teacher AI Sandbox!")\n',
  },
  {
    id: "c",
    label: "C",
    icon: "⚙️",
    monacoId: "c",
    defaultCode:
      '#include <stdio.h>\n\nint main() {\n    printf("Hello from Teacher AI Sandbox!\\n");\n    return 0;\n}\n',
  },
  {
    id: "cpp",
    label: "C++",
    icon: "⚡",
    monacoId: "cpp",
    defaultCode:
      '#include <iostream>\n\nint main() {\n    std::cout << "Hello from Teacher AI Sandbox!" << std::endl;\n    return 0;\n}\n',
  },
];

// WebSocket URL — derive from current page origin for flexibility
const host = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
const WS_URL = `ws://${host}:8000/ws/execute`;

export default function CodeEditor({ initialCode = "", initialLang = "python", activeVideo, onTakeQuiz, theme = "vs-dark" }) {
  const getLanguageConfig = (id) => LANGUAGES.find((l) => l.id === id) || LANGUAGES[0];
  const transcriptLoaded = Boolean(activeVideo?.transcript);

  const defaultFile = { id: "1", name: "main.py", language: "python", content: LANGUAGES[0].defaultCode };
  const [files, setFiles] = useState(() => {
    const saved = sessionStorage.getItem('aethernet_files');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed && parsed.length > 0) return parsed;
      } catch (e) { }
    }
    // Backward comp or first time
    if (initialCode) {
      return [{ ...defaultFile, language: initialLang, content: initialCode }];
    }
    return [defaultFile];
  });
  const [activeFileId, setActiveFileId] = useState(files[0].id);

  const activeFile = files.find(f => f.id === activeFileId) || files[0];
  const selectedLang = activeFile.language;
  const code = activeFile.content;

  const [isRunning, setIsRunning] = useState(false);
  const [exitStatus, setExitStatus] = useState(null); // "success" | "error" | null
  const [debugStatus, setDebugStatus] = useState(null); // null | "running" | "success" | "error"
  const [debugMessage, setDebugMessage] = useState("");

  const [isEditorExpanded, setIsEditorExpanded] = useState(false);
  const [isTerminalExpanded, setIsTerminalExpanded] = useState(false);

  const currentLang = getLanguageConfig(selectedLang);

  // -----------------------------------------------------------------------
  // Session Persistence: Save on Update
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (files && files.length > 0) {
      sessionStorage.setItem('aethernet_files', JSON.stringify(files));
    }
  }, [files]);

  // Refs for xterm.js
  const terminalContainerRef = useRef(null);
  const terminalRef = useRef(null);    // Terminal instance
  const fitAddonRef = useRef(null);    // FitAddon instance
  const wsRef = useRef(null);          // WebSocket instance
  const onDataDisposableRef = useRef(null); // xterm onData listener
  const terminalInitialized = useRef(false);
  const inputBuffer = useRef("");      // Local line buffer for interactive input
  const terminalOutputRef = useRef(""); // Raw output from backend
  const monacoEditorRef = useRef(null); // Reference to Monaco editor instance

  const handleEditorDidMount = (editor) => {
    monacoEditorRef.current = editor;
  };

  // Store code in a ref so the WebSocket callback always has the latest value
  const codeRef = useRef(code);
  const filesRef = useRef(files);
  const activeFileRef = useRef(activeFile);
  const selectedLangRef = useRef(selectedLang);
  
  useEffect(() => { codeRef.current = code; }, [code]);
  useEffect(() => { filesRef.current = files; }, [files]);
  useEffect(() => { activeFileRef.current = activeFile; }, [activeFile]);
  useEffect(() => { selectedLangRef.current = selectedLang; }, [selectedLang]);

  // Refit terminal when pane expansion states change
  useEffect(() => {
    if (fitAddonRef.current) {
      // Use a slight delay to ensure DOM and CSS transitions have completed
      setTimeout(() => {
        try {
          fitAddonRef.current.fit();
        } catch (e) {
          console.error("Fit error:", e);
        }
      }, 50);
      
      // Also try immediately just in case
      try {
        fitAddonRef.current.fit();
      } catch (e) {}
    }
  }, [isTerminalExpanded, isEditorExpanded]);

  // Update terminal theme
  useEffect(() => {
    if (!terminalRef.current) return;
    if (theme === "vs-light") {
      terminalRef.current.options.theme = {
        background: "#f1f5f9",
        foreground: "#0f172a",
        cursor: "#7c3aed",
        selectionBackground: "rgba(124, 58, 237, 0.2)",
        black: "#000000",
        red: "#ef4444",
        green: "#22c55e",
        yellow: "#eab308",
        blue: "#3b82f6",
        magenta: "#a855f7",
        cyan: "#06b6d4",
        white: "#0f172a",
        brightBlack: "#64748b",
        brightRed: "#f87171",
        brightGreen: "#4ade80",
        brightYellow: "#fde047",
        brightBlue: "#60a5fa",
        brightMagenta: "#c084fc",
        brightCyan: "#22d3ee",
        brightWhite: "#ffffff",
      };
    } else {
      terminalRef.current.options.theme = {
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
      };
    }
  }, [theme]);


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
    const ext = newLang === "python" ? "py" : newLang === "c" ? "c" : newLang === "javascript" ? "js" : newLang === "java" ? "java" : newLang === "bash" ? "sh" : "cpp";
    const newDefaultCode = getLanguageConfig(newLang).defaultCode;

    setFiles(prev => prev.map(f => {
      if (f.id === activeFileId) {
        let newName = f.name;
        // Strip common extensions and append the new one
        newName = newName.replace(/\.(py|c|cpp|js|java|sh|txt)$/i, '');
        newName = `${newName}.${ext}`;

        // Update content to new default if it's currently empty or matches the old default
        const oldDefaultCode = getLanguageConfig(f.language).defaultCode;
        let newContent = f.content;
        if (!f.content.trim() || f.content === oldDefaultCode) {
          newContent = newDefaultCode;
        }

        return { ...f, language: newLang, name: newName, content: newContent };
      }
      return f;
    }));
    
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
    setFiles((prev) => prev.map(f => f.id === activeFileId ? { ...f, content: value || "" } : f));
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
        files: filesRef.current.map(f => ({ name: f.name, content: f.content })),
        main_file: activeFileRef.current.name,
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
    const debugTargetFileId = activeFileRef.current?.id;

    setDebugStatus("running");
    setDebugMessage("✨ Connecting to Local Sandbox...");

    orchestrateDebug(
      { code: currentCode, language: lang, terminal_error: terminalError },
      // onChunk
      (chunk) => {
        if (chunk.type === "log") {
          setDebugMessage(`✨ ${chunk.message}`);
        } else if (chunk.type === "success") {
          setDebugStatus("success");
          if (chunk.code) {
            console.log("[CodeEditor] Magic Wand Success!");
            console.log("[CodeEditor] targeting file:", debugTargetFileId);
            console.log("[CodeEditor] chunk.code:", chunk.code);

            if (chunk.code !== currentCode) {
              setDebugMessage("✅ Code fixed and applied to editor!");
            } else {
              setDebugMessage("✅ AI attempted to fix, but code was unchanged.");
            }
            setFiles((prev) => {
              return prev.map(f => f.id === debugTargetFileId ? { ...f, content: chunk.code } : f);
            });
            // Forcefully bypass React state and explicitly tell Monaco Editor to update
            // Only if the debugged file is still the active one
            if (monacoEditorRef.current && activeFileRef.current?.id === debugTargetFileId) {
              monacoEditorRef.current.setValue(chunk.code);
            }
          }
          // Write clean output to terminal (skip raw JSON blobs)
          if (terminalRef.current && chunk.output) {
            const output = chunk.output.trim();
            // Don't write raw JSON structures to the terminal
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

  const headerActions = (
    <>
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

        {/* ✨ Magic Wand Debugger */}
        <button
          id="magic-wand-button"
          className="run-button run-button--secondary"
          style={debugStatus === "running" ? { backgroundColor: "#6d28d9" } : {}}
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
            "🤖 Debug with AI"
          )}
        </button>

      </div>
    </>
  );

  return (
    <div className="code-editor-container">
      {/* ── Inline Toolbar (was previously portalled to old header) ── */}
      <div className="code-editor-toolbar">
        {headerActions}
      </div>

      {/* Top Pane: Monaco Editor */}
      <div className={`editor-pane ${isEditorExpanded ? "expanded-pane" : ""}`}>
        <div className="editor-header">
          <div className="editor-tabs">
            {files.map(f => {
              const langConf = getLanguageConfig(f.language);
              return (
                <div 
                  key={f.id} 
                  className={`editor-tab ${f.id === activeFileId ? "active" : ""}`}
                  onClick={() => setActiveFileId(f.id)}
                >
                  <span className="editor-tab-icon">{langConf.icon}</span>
                  <span 
                    className="editor-tab-title" 
                    contentEditable
                    suppressContentEditableWarning
                    spellCheck={false}
                    onBlur={(e) => {
                       const newName = e.target.innerText.trim();
                       if(newName) {
                         let newLang = f.language;
                         if (newName.endsWith(".py")) newLang = "python";
                         else if (newName.endsWith(".c")) newLang = "c";
                         else if (newName.endsWith(".cpp")) newLang = "cpp";
                         else if (newName.endsWith(".js")) newLang = "javascript";
                         else if (newName.endsWith(".java")) newLang = "java";
                         else if (newName.endsWith(".sh")) newLang = "bash";
                         
                         setFiles(prev => prev.map(pf => pf.id === f.id ? {...pf, name: newName, language: newLang} : pf));
                       }
                    }}
                    onKeyDown={(e) => { if(e.key === 'Enter') { e.preventDefault(); e.target.blur(); } }}
                  >
                    {f.name}
                  </span>
                  {files.length > 1 && (
                    <button 
                      className="editor-tab-close" 
                      onClick={(e) => {
                        e.stopPropagation();
                        setFiles(prev => prev.filter(pf => pf.id !== f.id));
                        if(activeFileId === f.id) {
                          const remaining = files.filter(pf => pf.id !== f.id);
                          if(remaining.length > 0) setActiveFileId(remaining[0].id);
                        }
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
              );
            })}
            <button 
              className="icon-btn" 
              style={{ marginLeft: '4px', padding: '4px' }}
              title="Add File"
              onClick={() => {
                const newId = Date.now().toString();
                const newLang = selectedLang;
                const ext = newLang === "python" ? "py" : newLang === "c" ? "c" : newLang === "javascript" ? "js" : newLang === "java" ? "java" : newLang === "bash" ? "sh" : "cpp";
                const langConfig = getLanguageConfig(newLang);
                
                setFiles(prev => [...prev, { 
                  id: newId, 
                  name: `file_${prev.length+1}.${ext}`, 
                  language: newLang, 
                  content: langConfig.defaultCode 
                }]);
                setActiveFileId(newId);
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            </button>
          </div>
          <div className="editor-window-actions">
            <button className="icon-btn" title={isEditorExpanded ? "Collapse" : "Expand"} onClick={() => setIsEditorExpanded(!isEditorExpanded)}>
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                 {isEditorExpanded ? (
                    <><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></>
                 ) : (
                    <><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></>
                 )}
               </svg>
            </button>
          </div>
        </div>

        <div className="editor-wrapper">
          <Editor
            height="100%"
            language={currentLang.monacoId}
            theme={theme}
            value={code}
            onChange={handleEditorChange}
            onMount={handleEditorDidMount}
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
      <div className={`terminal-pane ${isTerminalExpanded ? "expanded-pane" : ""}`}>
        <div className="terminal-header">
          <div className="terminal-title">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ marginRight: "8px", verticalAlign: "-2px" }}
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
            Terminal
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ marginLeft: "8px", verticalAlign: "-2px", color: "var(--color-text-muted)" }}
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </div>
          <div className="terminal-actions">
            {exitStatus && (
              <span
                className={`terminal-badge ${exitStatus === "error" ? "badge-error" : "badge-success"
                  }`}
              >
                {exitStatus === "error" ? "Failed" : "Success"}
              </span>
            )}
            <button className="icon-text-btn" onClick={() => terminalRef.current?.clear()}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
              Clear
            </button>
            <button className="icon-btn" title={isTerminalExpanded ? "Collapse" : "Expand"} onClick={() => setIsTerminalExpanded(!isTerminalExpanded)}>
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                 {isTerminalExpanded ? (
                    <><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></>
                 ) : (
                    <><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></>
                 )}
               </svg>
            </button>
          </div>
        </div>
        {debugMessage && (
          <div style={{
            padding: "6px 14px",
            fontSize: "12px",
            fontFamily: "'Fira Code', monospace",
            background: debugStatus === "error" ? "rgba(239,68,68,0.15)" : debugStatus === "success" ? "rgba(34,197,94,0.15)" : "rgba(45,212,191,0.15)",
            color: debugStatus === "error" ? "#f87171" : debugStatus === "success" ? "#4ade80" : "#2dd4bf",
            borderBottom: "1px solid rgba(45,212,191,0.2)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}>
            {debugStatus === "running" && (
              <span style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#2dd4bf", animation: "pulse 1.5s ease-in-out infinite" }} />
            )}
            {debugMessage}
          </div>
        )}
        <div className="xterm-container" ref={terminalContainerRef} />
      </div>
    </div>
  );
}
