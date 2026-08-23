import { HeartPulse, Hospital, UserRound, ShieldCheck, BarChart3 } from 'lucide-react'
import styles from './Hero.module.css'

export default function Hero({ onGetStarted }) {
  const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })

  return (
    <section className={styles.hero} aria-labelledby="hero-heading">
      <div className={styles.inner}>

        {/* ── Text column ── */}
        <div className={styles.text}>
          <div className={styles.eyebrow} aria-hidden="true">
            <HeartPulse size={14} strokeWidth={2} />
            Clinical Healthcare Platform
          </div>

          <h1 id="hero-heading" className={styles.heading}>
            Connected Care.<br />
            <span className={styles.accent}>Smarter Healthcare.</span>
          </h1>

          <p className={styles.sub}>
            A unified healthcare platform connecting patients, hospitals, and healthcare
            management through a secure digital experience.
          </p>

          <div className={styles.ctas}>
            <button className={styles.primary} onClick={onGetStarted}>
              Get Started
            </button>
            <button className={styles.secondary} onClick={() => scrollTo('capabilities')}>
              Learn More
            </button>
          </div>

          <div className={styles.trust} role="list">
            {[
              { icon: <ShieldCheck size={15} strokeWidth={2} />, label: 'Secure Access' },
              { icon: <Hospital    size={15} strokeWidth={2} />, label: 'Hospital Ready' },
              { icon: <UserRound   size={15} strokeWidth={2} />, label: 'Patient Focused' },
            ].map(t => (
              <div key={t.label} className={styles.trustItem} role="listitem">
                <span className={styles.trustIcon} aria-hidden="true">{t.icon}</span>
                <span>{t.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Visual column ── */}
        <div className={styles.visual} aria-hidden="true">
          <HeroVisual />
        </div>
      </div>
    </section>
  )
}

/* ─────────────────────────────────────────────────────────────────
   HeroVisual — 100% SVG diagram so lines always align with boxes.

   ViewBox: 400 × 380
   Hub centre: (200, 190)
   Node centres (box centre):
     Patient    TL: (72,  72)
     Hospital   TR: (328, 72)
     Management BL: (72,  308)
     Security   BR: (328, 308)

   Each node box is 80×80 px.  Lines run from hub centre to the
   nearest corner of each node box, so they never overlap the icons.
───────────────────────────────────────────────────────────────── */
function HeroVisual() {
  const HUB = { x: 200, y: 190, w: 100, h: 100, r: 18 }
  const NODE_SIZE = 80
  const HALF = NODE_SIZE / 2

  const nodes = [
    { id: 'patient',    cx: 72,  cy: 72,  label: 'Patient',    icon: UserRound,   labelSide: 'bottom' },
    { id: 'hospital',   cx: 328, cy: 72,  label: 'Hospital',   icon: Hospital,    labelSide: 'bottom' },
    { id: 'management', cx: 72,  cy: 308, label: 'Management', icon: BarChart3,   labelSide: 'top'    },
    { id: 'security',   cx: 328, cy: 308, label: 'Security',   icon: ShieldCheck, labelSide: 'top'    },
  ]

  /* Compute line endpoints: from hub edge toward node centre,
     and from node edge toward hub centre, so lines stay outside both boxes. */
  const hubLeft   = HUB.x - HUB.w / 2   // 150
  const hubRight  = HUB.x + HUB.w / 2   // 250
  const hubTop    = HUB.y - HUB.h / 2   // 140
  const hubBottom = HUB.y + HUB.h / 2   // 240

  function lineEndpoints(node) {
    const dx = node.cx - HUB.x
    const dy = node.cy - HUB.y

    // Hub side: pick the corner of the hub bounding box closest to the node
    const hx = dx < 0 ? hubLeft  : hubRight
    const hy = dy < 0 ? hubTop   : hubBottom

    // Node side: pick the corner of the node bounding box closest to the hub
    const nx = dx < 0 ? node.cx + HALF : node.cx - HALF
    const ny = dy < 0 ? node.cy + HALF : node.cy - HALF

    return { x1: hx, y1: hy, x2: nx, y2: ny }
  }

  return (
    <svg
      viewBox="0 0 400 380"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={styles.diagram}
      role="img"
      aria-label="CTS Healthcare connected care network: Patient, Hospital, Management and Security nodes linked to a central hub"
    >
      {/* ── Ambient rings (purely decorative) ── */}
      <circle cx="200" cy="190" r="130" stroke="#006EB6" strokeWidth="1" opacity="0.07" />
      <circle cx="200" cy="190" r="165" stroke="#006EB6" strokeWidth="1" opacity="0.04" />

      {/* ── Dashed connector lines ── */}
      {nodes.map(n => {
        const { x1, y1, x2, y2 } = lineEndpoints(n)
        return (
          <line
            key={`line-${n.id}`}
            x1={x1} y1={y1} x2={x2} y2={y2}
            stroke="#3BB7B2"
            strokeWidth="1.5"
            strokeDasharray="5 4"
            opacity="0.55"
          />
        )
      })}

      {/* ── Satellite node boxes ── */}
      {nodes.map(n => {
        const x = n.cx - HALF
        const y = n.cy - HALF
        const IconComp = n.icon
        const LABEL_OFFSET = 14

        return (
          <g key={n.id}>
            {/* Node box */}
            <rect
              x={x} y={y}
              width={NODE_SIZE} height={NODE_SIZE}
              rx="14"
              fill="rgba(255,255,255,0.07)"
              stroke="rgba(255,255,255,0.18)"
              strokeWidth="1"
            />

            {/* Icon — centred in box via foreignObject */}
            <foreignObject
              x={x + (NODE_SIZE - 28) / 2}
              y={y + (NODE_SIZE - 28) / 2}
              width="28"
              height="28"
            >
              <div xmlns="http://www.w3.org/1999/xhtml"
                style={{ display:'flex', alignItems:'center', justifyContent:'center', width:'100%', height:'100%', color:'#3BB7B2' }}>
                <IconComp size={26} strokeWidth={1.5} />
              </div>
            </foreignObject>

            {/* Label — positioned above or below the box */}
            <text
              x={n.cx}
              y={n.labelSide === 'bottom' ? y + NODE_SIZE + LABEL_OFFSET : y - LABEL_OFFSET + 2}
              textAnchor="middle"
              dominantBaseline={n.labelSide === 'bottom' ? 'hanging' : 'auto'}
              fontSize="11"
              fontWeight="600"
              fontFamily="'Source Sans 3', sans-serif"
              fill="rgba(255,255,255,0.75)"
              letterSpacing="0.02em"
            >
              {n.label}
            </text>
          </g>
        )
      })}

      {/* ── Central hub ── */}
      <rect
        x={HUB.x - HUB.w / 2} y={HUB.y - HUB.h / 2}
        width={HUB.w} height={HUB.h}
        rx={HUB.r}
        fill="#006EB6"
        stroke="rgba(255,255,255,0.2)"
        strokeWidth="1.5"
      />
      {/* Hub glow */}
      <rect
        x={HUB.x - HUB.w / 2} y={HUB.y - HUB.h / 2}
        width={HUB.w} height={HUB.h}
        rx={HUB.r}
        fill="none"
        stroke="#006EB6"
        strokeWidth="16"
        opacity="0.15"
      />

      {/* Hub icon — HeartPulse centred */}
      <foreignObject x={HUB.x - 18} y={HUB.y - 26} width="36" height="36">
        <div xmlns="http://www.w3.org/1999/xhtml"
          style={{ display:'flex', alignItems:'center', justifyContent:'center', width:'100%', height:'100%', color:'white' }}>
          <HeartPulse size={32} strokeWidth={1.6} />
        </div>
      </foreignObject>

      {/* Hub label */}
      <text
        x={HUB.x}
        y={HUB.y + 22}
        textAnchor="middle"
        fontSize="8.5"
        fontWeight="700"
        fontFamily="'Source Sans 3', sans-serif"
        fill="rgba(255,255,255,0.85)"
        letterSpacing="0.06em"
      >
        CTS HEALTHCARE
      </text>

      {/* ── "Connected Care" footer label ── */}
      <text
        x="200" y="365"
        textAnchor="middle"
        fontSize="10"
        fontWeight="700"
        fontFamily="'Source Sans 3', sans-serif"
        fill="rgba(255,255,255,0.3)"
        letterSpacing="0.1em"
      >
        CONNECTED CARE
      </text>
    </svg>
  )
}
