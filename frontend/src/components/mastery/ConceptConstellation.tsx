import { useState } from "react";
import type { LearnerDocumentConceptItem } from "../../types/api";
import { CitationIcon, CheckCircleIcon, SparklesIcon } from "../common/Icons";

interface ConceptConstellationProps {
  concepts: LearnerDocumentConceptItem[];
}

export function ConceptConstellation({ concepts }: ConceptConstellationProps) {
  const [selectedConcept, setSelectedConcept] = useState<LearnerDocumentConceptItem | null>(
    concepts.length > 0 ? concepts[0] : null
  );

  if (concepts.length === 0) return null;

  // Calculate circular layout positions for nodes
  const width = 600;
  const height = 360;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(centerX, centerY) - 50;

  const nodePositions = concepts.map((c, i) => {
    const angle = (i / concepts.length) * 2 * Math.PI - Math.PI / 2;
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    return { ...c, x, y };
  });

  const nodeMap = new Map(nodePositions.map((n) => [n.concept_label.toLowerCase(), n]));

  // Build edges based on related_concept_names
  const edges: { x1: number; y1: number; x2: number; y2: number; key: string }[] = [];
  nodePositions.forEach((source) => {
    source.related_concept_names.forEach((relName) => {
      const target = nodeMap.get(relName.toLowerCase());
      if (target && target.concept_id !== source.concept_id) {
        edges.push({
          x1: source.x,
          y1: source.y,
          x2: target.x,
          y2: target.y,
          key: `${source.concept_id}-${target.concept_id}`,
        });
      }
    });
  });

  const getNodeColor = (status: string) => {
    switch (status) {
      case "proficient":
        return "#10b981";
      case "struggling":
        return "#f43f5e";
      case "learning":
        return "#f59e0b";
      default:
        return "#64748b";
    }
  };

  return (
    <div className="concept-constellation-card surface-card p-6 mb-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <span className="section-subtitle">INTERACTIVE KNOWLEDGE MAP</span>
          <h3 className="text-lg font-semibold mt-0.5">Concept Mastery Constellation</h3>
        </div>
        <div className="flex items-center gap-3 text-xs font-mono">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald" /> Proficient
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber" /> Learning
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose" /> Struggling
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-slate" /> Unattempted
          </span>
        </div>
      </div>

      <div className="constellation-layout">
        {/* SVG Graph Canvas */}
        <div className="constellation-canvas-wrapper">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="constellation-svg"
            role="img"
            aria-label="Concept relationship map"
          >
            <defs>
              <filter id="glow-node" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Connecting Edges */}
            {edges.map((edge) => (
              <line
                key={edge.key}
                x1={edge.x1}
                y1={edge.y1}
                x2={edge.x2}
                y2={edge.y2}
                stroke="rgba(255, 255, 255, 0.12)"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
            ))}

            {/* Concept Nodes */}
            {nodePositions.map((node) => {
              const isSelected = selectedConcept?.concept_id === node.concept_id;
              const color = getNodeColor(node.learning_status);

              return (
                <g
                  key={node.concept_id}
                  className="constellation-node-group"
                  onClick={() => setSelectedConcept(node)}
                  tabIndex={0}
                  role="button"
                  aria-label={`Concept ${node.concept_label}`}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      setSelectedConcept(node);
                    }
                  }}
                >
                  {/* Outer selection ring */}
                  {isSelected && (
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r="22"
                      fill="none"
                      stroke="#38bdf8"
                      strokeWidth="2"
                      filter="url(#glow-node)"
                    />
                  )}

                  {/* Core Node */}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={isSelected ? "15" : "12"}
                    fill="#0d121c"
                    stroke={color}
                    strokeWidth="2.5"
                    filter="url(#glow-node)"
                  />

                  {/* Label */}
                  <text
                    x={node.x}
                    y={node.y + 26}
                    textAnchor="middle"
                    fill={isSelected ? "#f8fafc" : "#94a3b8"}
                    fontSize="11"
                    fontFamily="Inter, sans-serif"
                    fontWeight={isSelected ? "600" : "500"}
                  >
                    {node.concept_label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Selected Concept Preview Card */}
        {selectedConcept && (
          <div className="constellation-inspector-card">
            <div className="flex items-center justify-between mb-2">
              <span className="font-serif font-bold text-lg text-primary">
                {selectedConcept.concept_label}
              </span>
              <span className={`status-badge badge-${selectedConcept.learning_status}`}>
                {selectedConcept.learning_status.replace("_", " ").toUpperCase()}
              </span>
            </div>

            <div className="flex items-baseline gap-2 mb-3">
              <span className="text-xl font-mono font-bold text-cyan">
                {selectedConcept.mastery_estimate != null
                  ? `${Math.round(selectedConcept.mastery_estimate * 100)}%`
                  : "0%"}
              </span>
              <span className="text-xs text-muted">
                ({selectedConcept.correct_count} of {selectedConcept.attempt_count} correct)
              </span>
            </div>

            <p className="text-xs text-secondary leading-relaxed mb-3">
              {selectedConcept.explanation}
            </p>

            <div className="p-2.5 bg-surface-elevated rounded border border-subtle mb-3">
              <span className="text-2xs font-mono font-bold text-violet block mb-1">
                ACTION:
              </span>
              <span className="text-xs text-primary">{selectedConcept.recommended_action}</span>
            </div>

            <div className="text-xs text-muted flex items-center gap-1.5">
              <CitationIcon className="w-3.5 h-3.5 text-cyan" />
              <span>
                {selectedConcept.source_type === "pdf_page" ? "Page" : "Slide"}{" "}
                {selectedConcept.page_or_slide_number}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
