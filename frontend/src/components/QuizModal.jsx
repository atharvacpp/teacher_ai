/**
 * QuizModal.jsx — Focus Mode Interactive Quiz Window.
 *
 * A full-screen, distraction-free quiz overlay that:
 *   • Generates questions from a video transcript via Qwen 2.5
 *   • Displays all questions at once in a scrollable form
 *   • Lets the user select one answer per question
 *   • Grades everything on "Submit" and shows score + wrong-answer explanations
 */

import { useState, useEffect, useRef } from "react";
import { generateQuiz } from "../services/api";

// ─── Stage Constants ─────────────────────────────────────────────────────────
const STAGE_LOADING  = "loading";
const STAGE_QUIZ     = "quiz";
const STAGE_RESULTS  = "results";
const STAGE_ERROR    = "error";

export default function QuizModal({ videoId, videoTitle, videoTranscript, onClose }) {
  const [stage, setStage]           = useState(STAGE_LOADING);
  const [quiz, setQuiz]             = useState(null);
  const [error, setError]           = useState(null);
  const [answers, setAnswers]       = useState({});   // { questionIndex: selectedOptionText }
  const [score, setScore]           = useState(0);
  const [retryTrigger, setRetryTrigger] = useState(0);
  const topRef                      = useRef(null);

  // ─── Fetch quiz on mount ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function fetchQuiz() {
      try {
        const result = await generateQuiz(videoId, videoTitle, videoTranscript);
        if (!cancelled) {
          setQuiz(result);
          setStage(STAGE_QUIZ);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setStage(STAGE_ERROR);
        }
      }
    }

    fetchQuiz();
    return () => { cancelled = true; };
  }, [videoId, videoTitle, videoTranscript, retryTrigger]);

  // ─── Handlers ───────────────────────────────────────────────────────────

  function handleSelect(questionIndex, optionText) {
    if (stage !== STAGE_QUIZ) return;
    setAnswers((prev) => ({ ...prev, [questionIndex]: optionText }));
  }

  function handleSubmit() {
    if (!quiz) return;
    let correct = 0;
    quiz.questions.forEach((q, i) => {
      if (answers[i] === q.correct_answer) correct++;
    });
    setScore(correct);
    setStage(STAGE_RESULTS);
    // Scroll to top of results
    topRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handleRetry() {
    setAnswers({});
    setScore(0);
    setQuiz(null);
    setStage(STAGE_LOADING);
    setRetryTrigger(prev => prev + 1);
    topRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ─── Derived state ─────────────────────────────────────────────────────
  const totalQuestions  = quiz?.questions?.length || 0;
  const answeredCount   = Object.keys(answers).length;
  const allAnswered     = answeredCount === totalQuestions;
  const pct             = totalQuestions > 0 ? score / totalQuestions : 0;

  function getScoreEmoji() {
    if (pct === 1)    return "🏆";
    if (pct >= 0.8)   return "🎉";
    if (pct >= 0.6)   return "👍";
    if (pct >= 0.4)   return "📚";
    return "💪";
  }

  function getScoreMessage() {
    if (pct === 1)    return "Perfect score! You've mastered this material!";
    if (pct >= 0.8)   return "Excellent work! You have a strong understanding.";
    if (pct >= 0.6)   return "Good job! Review the explanations below to fill in the gaps.";
    if (pct >= 0.4)   return "Decent effort! The explanations below will help you improve.";
    return "Keep learning! Review the explanations and try the quiz again.";
  }

  // ─── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="focus-overlay">
      <div className="focus-window" ref={topRef}>

        {/* ── Top Bar ── */}
        <div className="focus-topbar">
          <div className="focus-topbar__left">
            <span className="focus-topbar__icon">🎯</span>
            <span className="focus-topbar__title">Focus Mode</span>
            {stage === STAGE_QUIZ && (
              <span className="focus-topbar__count">
                {answeredCount}/{totalQuestions} answered
              </span>
            )}
          </div>
          <button className="focus-topbar__close" onClick={onClose} title="Exit Focus Mode">
            ✕
          </button>
        </div>

        {/* ── Loading ── */}
        {stage === STAGE_LOADING && (
          <div className="focus-center">
            <div className="focus-spinner" />
            <h2 className="focus-center__title">Generating Your Quiz</h2>
            <p className="focus-center__subtitle">
              Qwen 2.5 is analyzing the transcript for <em>"{videoTitle}"</em>…
            </p>
          </div>
        )}

        {/* ── Error ── */}
        {stage === STAGE_ERROR && (
          <div className="focus-center">
            <div className="focus-center__emoji">⚠️</div>
            <h2 className="focus-center__title">Quiz Generation Failed</h2>
            <p className="focus-center__subtitle">{error}</p>
            <button className="focus-btn focus-btn--primary" onClick={onClose}>
              Close
            </button>
          </div>
        )}

        {/* ── Quiz Form (all questions at once) ── */}
        {stage === STAGE_QUIZ && quiz && (
          <div className="focus-body">
            <div className="focus-quiz-header">
              <h1 className="focus-quiz-title">{quiz.quiz_title}</h1>
              <p className="focus-quiz-subtitle">
                Answer all {totalQuestions} questions, then hit Submit to see your score.
              </p>
            </div>

            <div className="focus-questions">
              {quiz.questions.map((q, qIdx) => (
                <div className="focus-question-card" key={qIdx}>
                  <div className="focus-question-number">
                    <span>{qIdx + 1}</span>
                  </div>
                  <p className="focus-question-text">{q.question_text}</p>
                  <div className="focus-options">
                    {q.options.map((option, oIdx) => {
                      const isSelected = answers[qIdx] === option;
                      return (
                        <button
                          key={oIdx}
                          className={`focus-option ${isSelected ? "focus-option--selected" : ""}`}
                          onClick={() => handleSelect(qIdx, option)}
                        >
                          <span className="focus-option__letter">
                            {String.fromCharCode(65 + oIdx)}
                          </span>
                          <span className="focus-option__text">{option}</span>
                          {isSelected && <span className="focus-option__check">✓</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="focus-submit-bar">
              <button
                className={`focus-btn focus-btn--submit ${allAnswered ? "" : "focus-btn--disabled"}`}
                onClick={handleSubmit}
                disabled={!allAnswered}
              >
                {allAnswered
                  ? `Submit Quiz (${totalQuestions}/${totalQuestions}) 🚀`
                  : `Answer all questions (${answeredCount}/${totalQuestions})`
                }
              </button>
            </div>
          </div>
        )}

        {/* ── Results ── */}
        {stage === STAGE_RESULTS && quiz && (
          <div className="focus-body">
            {/* Score Banner */}
            <div className="focus-score-banner">
              <div className="focus-score-emoji">{getScoreEmoji()}</div>
              <div className="focus-score-info">
                <h2 className="focus-score-heading">
                  {score}<span className="focus-score-divider">/</span>{totalQuestions}
                </h2>
                <p className="focus-score-message">{getScoreMessage()}</p>
              </div>
            </div>

            {/* Question Review */}
            <div className="focus-review">
              {quiz.questions.map((q, qIdx) => {
                const userAnswer = answers[qIdx];
                const isCorrect  = userAnswer === q.correct_answer;

                return (
                  <div
                    className={`focus-review-card ${isCorrect ? "focus-review-card--correct" : "focus-review-card--wrong"}`}
                    key={qIdx}
                  >
                    <div className="focus-review-header">
                      <span className="focus-review-number">{qIdx + 1}</span>
                      <span className={`focus-review-badge ${isCorrect ? "focus-review-badge--correct" : "focus-review-badge--wrong"}`}>
                        {isCorrect ? "✓ Correct" : "✗ Wrong"}
                      </span>
                    </div>

                    <p className="focus-review-question">{q.question_text}</p>

                    <div className="focus-review-answers">
                      {q.options.map((option, oIdx) => {
                        let cls = "focus-review-option";
                        if (option === q.correct_answer) {
                          cls += " focus-review-option--correct";
                        } else if (option === userAnswer && !isCorrect) {
                          cls += " focus-review-option--wrong";
                        } else {
                          cls += " focus-review-option--muted";
                        }
                        return (
                          <div className={cls} key={oIdx}>
                            <span className="focus-review-option__letter">
                              {String.fromCharCode(65 + oIdx)}
                            </span>
                            <span className="focus-review-option__text">{option}</span>
                            {option === q.correct_answer && (
                              <span className="focus-review-option__icon">✓</span>
                            )}
                            {option === userAnswer && !isCorrect && (
                              <span className="focus-review-option__icon">✗</span>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Explanation — only shown for wrong answers */}
                    {!isCorrect && (
                      <div className="focus-review-explanation">
                        <span className="focus-review-explanation__label">💡 Explanation</span>
                        <p className="focus-review-explanation__text">{q.explanation_if_wrong}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Bottom Actions */}
            <div className="focus-submit-bar">
              <button className="focus-btn focus-btn--secondary" onClick={handleRetry}>
                🔄 Retry Quiz
              </button>
              <button className="focus-btn focus-btn--primary" onClick={onClose}>
                Exit Focus Mode
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
