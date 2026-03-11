import { useState } from "react";
import type { QuizQuestion } from "../api";
import styles from "./QuizSection.module.css";

interface Props {
  quiz: QuizQuestion[];
}

export default function QuizSection({ quiz }: Props) {
  const [answers, setAnswers] = useState<number[]>(quiz.map(() => -1));

  if (quiz.length === 0) return null;

  function selectAnswer(qIndex: number, optIndex: number) {
    const next = [...answers];
    next[qIndex] = optIndex;
    setAnswers(next);
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <p className={styles.title}>Test your knowledge</p>
        <div className={styles.questions}>
        {quiz.map((q, qi) => (
          <div key={qi} className={styles.question}>
            <p className={styles.questionText}>{q.q}</p>
            <div className={styles.options}>
              {q.options.map((opt, oi) => {
                const selected = answers[qi] === oi;
                const answered = answers[qi] !== -1;
                const isCorrect = oi === q.answer;
                const showCorrectHighlight = answered && !selected && isCorrect;

                let indicator: string | null = null;
                let optClass = styles.option;
                if (selected) {
                  indicator = isCorrect ? "✓" : "✗";
                  optClass = isCorrect ? `${styles.option} ${styles.correct}` : `${styles.option} ${styles.wrong}`;
                } else if (showCorrectHighlight) {
                  optClass = `${styles.option} ${styles.correct}`;
                }

                return (
                  <button
                    key={oi}
                    className={optClass}
                    onClick={() => selectAnswer(qi, oi)}
                  >
                    {opt}
                    {indicator && <span className={styles.indicator}>{indicator}</span>}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        </div>
      </div>
    </div>
  );
}
