import type { PropsWithChildren, ReactNode } from "react";
import { motion } from "framer-motion";

interface SectionCardProps extends PropsWithChildren {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  className?: string;
}

export function SectionCard({
  title,
  eyebrow,
  actions,
  className,
  children
}: SectionCardProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className={`section-card ${className ?? ""}`.trim()}
    >
      <header className="section-card__header">
        <div>
          {eyebrow ? <p className="section-card__eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
        {actions ? <div className="section-card__actions">{actions}</div> : null}
      </header>
      {children}
    </motion.section>
  );
}

