import type { FurtherReadingItem } from "../api";
import styles from "./FurtherReadingSection.module.css";

interface Props {
  furtherReading: FurtherReadingItem[];
}

export default function FurtherReadingSection({ furtherReading }: Props) {
  if (furtherReading.length === 0) return null;

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <p className={styles.title}><span className={styles.icon}>📚</span> Further Reading</p>
        <ul className={styles.list}>
          {furtherReading.map((item, i) => (
            <li key={i} className={styles.item}>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.link}
              >
                {item.title}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
