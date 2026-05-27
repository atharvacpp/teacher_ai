/**
 * App.jsx — Root component for the ExplainAI React frontend.
 *
 * Renders the ChatInterface as the sole top-level view.
 * Future phases will add routing for video / audio features here.
 */

import React from "react";
import ChatInterface from "./components/ChatInterface";
import "./App.css";

export default function App() {
  return (
    <div className="app">
      <ChatInterface />
    </div>
  );
}
