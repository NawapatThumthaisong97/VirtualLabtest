import styles from './CoursePageHeader.module.css';

type CoursePageHeaderProps = {
  title: string;
};

export default function CoursePageHeader({ title }: CoursePageHeaderProps) {
  return (
    <header className={styles.headerShell}>
      <div className={styles.titleRow}>
        <h1 className={styles.titleText}>{title}</h1>
      </div>
    </header>
  );
}
