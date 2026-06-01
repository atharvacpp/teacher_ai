/**
 * App.jsx — Root component for the ExplainAI React frontend.
 *
 * Renders the ChatInterface and CodeEditor in a dashboard layout.
 */

import React from "react";
import ChatInterface from "./components/ChatInterface";
import CodeEditor from "./components/CodeEditor";
import "./App.css";

export default function App() {
  return (
    <div className="app">
      <div className="dashboard-layout">
        <ChatInterface />
        <CodeEditor />
      </div>
    </div>
  );
}
