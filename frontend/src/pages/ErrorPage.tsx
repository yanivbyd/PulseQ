import styles from "./ErrorPage.module.css";

export default function ErrorPage() {
  return (
    <div className={styles.container}>
      <h1>404</h1>
      <p>Page not found.</p>
      <a href="/">← Back to home</a>
    </div>
  );
}
