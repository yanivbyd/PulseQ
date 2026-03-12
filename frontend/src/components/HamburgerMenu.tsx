import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import styles from "./HamburgerMenu.module.css";

const NAV_LINKS = [
  { label: "Articles", to: "/", icon: "📰" },
  { label: "Topics", to: "/topics", icon: "🗂️" },
  { label: "New Article", to: "/generate", icon: "✏️" },
];

export default function HamburgerMenu() {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onMouseDown(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={wrapperRef} className={styles.wrapper}>
      <button
        className={styles.toggle}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "✕" : "☰"}
      </button>
      {open && (
        <nav className={styles.menu}>
          <div className={styles.menuHeader}>Navigate</div>
          {NAV_LINKS.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              aria-label={link.label}
              className={styles.link}
              onClick={() => setOpen(false)}
            >
              <span aria-hidden="true" className={styles.linkIcon}>{link.icon}</span>
              {link.label}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}
