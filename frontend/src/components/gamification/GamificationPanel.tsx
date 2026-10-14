import { useApp } from "../../context/AppContext";
import {
  CheckCircleIcon,
  SparklesIcon,
  TargetIcon,
  QuizIcon,
  RefreshIcon,
} from "../common/Icons";

export function GamificationPanel() {
  const { gamification, refreshGamification } = useApp();

  if (!gamification) {
    return (
      <div className="surface-card p-6 flex items-center justify-center text-muted">
        <RefreshIcon className="w-5 h-5 spin mr-2" />
        <span>Loading learner achievements & gamification...</span>
      </div>
    );
  }

  const {
    xp,
    level,
    level_title,
    xp_for_current_level,
    xp_for_next_level,
    level_progress_percentage,
    current_streak_days,
    achievements,
    daily_missions,
  } = gamification;

  return (
    <div className="gamification-panel-root surface-card p-6">
      {/* Level & XP Header Row */}
      <div className="gamification-header-row mb-6">
        <div className="flex items-center gap-4">
          <div className="level-hexagon">
            <span className="level-num">{level}</span>
            <span className="level-tag">LVL</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="level-title-text">{level_title}</span>
              <span className="badge badge-warning">
                <SparklesIcon className="w-3 h-3" /> {xp} XP
              </span>
            </div>
            <div className="xp-bar-wrapper mt-2">
              <div className="progress-bar-track">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${level_progress_percentage}%` }}
                />
              </div>
              <span className="xp-meta-text">
                {xp} / {xp_for_next_level} XP to Level {level + 1} ({level_progress_percentage}%)
              </span>
            </div>
          </div>
        </div>

        {/* Streak Jewel */}
        <div className="streak-card">
          <span className="streak-icon">⚡</span>
          <div className="streak-meta">
            <span className="streak-number">{current_streak_days} DAY{current_streak_days === 1 ? "" : "S"}</span>
            <span className="streak-label">ACTIVE STREAK</span>
          </div>
        </div>
      </div>

      {/* 2-Column: Daily Missions & Achievements */}
      <div className="gamification-subgrid">
        {/* Daily Missions */}
        <div className="missions-column">
          <div className="flex items-center justify-between mb-3">
            <span className="section-subtitle">TODAY'S MISSIONS</span>
            <span className="text-xs font-mono text-muted">
              {daily_missions.filter((m) => m.completed).length}/{daily_missions.length} DONE
            </span>
          </div>

          <div className="missions-list">
            {daily_missions.map((m) => (
              <div
                key={m.id}
                className={`mission-item ${m.completed ? "mission-completed" : ""}`}
              >
                <div className="mission-check">
                  {m.completed ? (
                    <CheckCircleIcon className="w-4 h-4 text-emerald" />
                  ) : (
                    <span className="mission-uncheck" />
                  )}
                </div>
                <div className="mission-info">
                  <span className="mission-title">{m.title}</span>
                  <span className="mission-desc">{m.description}</span>
                </div>
                <span className="mission-reward">+{m.xp_reward} XP</span>
              </div>
            ))}
          </div>
        </div>

        {/* Achievements Showcase */}
        <div className="achievements-column">
          <div className="flex items-center justify-between mb-3">
            <span className="section-subtitle">UNLOCKED ACHIEVEMENTS</span>
            <span className="text-xs font-mono text-muted">
              {achievements.filter((a) => a.unlocked).length}/{achievements.length} UNLOCKED
            </span>
          </div>

          <div className="achievements-badge-grid">
            {achievements.map((a) => (
              <div
                key={a.id}
                className={`achievement-card ${
                  a.unlocked ? "achievement-unlocked" : "achievement-locked"
                }`}
                title={a.unlocked ? `Unlocked: ${a.description}` : `Locked: ${a.description}`}
              >
                <div className="achievement-icon">
                  {a.unlocked ? "🏆" : "🔒"}
                </div>
                <div className="achievement-meta">
                  <span className="achievement-title">{a.title}</span>
                  <span className="achievement-desc">{a.description}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
