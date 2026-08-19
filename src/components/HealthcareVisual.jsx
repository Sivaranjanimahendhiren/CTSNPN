import styles from './HealthcareVisual.module.css'

/**
 * HealthcareVisual — abstract connected-care network illustration.
 * All node icons are hand-authored SVG paths, perfectly centred inside
 * their respective circles.  No emoji, no external assets.
 *
 * Coordinate system: viewBox="0 0 520 440"
 * Hub centre: (260, 220)
 * Node centres: Hospital(108,108) Admin(412,108) Patient(80,318) Records(440,318) Data(260,390)
 */
export default function HealthcareVisual() {
  // shared design tokens
  const C_PRIMARY  = '#004B76'
  const C_TEAL     = '#008C95'
  const C_AQUA     = '#3BB7B2'
  const C_BG_RING1 = '#E6F3F8'
  const C_BG_RING2 = '#D0E9F0'
  const C_NODE_BG  = '#FFFFFF'
  const C_NODE_STR = '#D8E5EA'
  const C_ICON     = '#004B76'
  const C_LINE     = '#3BB7B2'

  // Node definitions — cx/cy are the circle centres
  const nodes = [
    { cx: 108, cy: 108, r: 36, label: 'Hospital',   icon: 'hospital' },
    { cx: 412, cy: 108, r: 36, label: 'CMS / Admin', icon: 'admin'    },
    { cx:  80, cy: 318, r: 32, label: 'Patient',    icon: 'patient'  },
    { cx: 440, cy: 318, r: 32, label: 'Records',    icon: 'records'  },
    { cx: 260, cy: 395, r: 28, label: 'Data',       icon: 'data'     },
  ]

  return (
    <div className={styles.wrapper}>
      <svg
        viewBox="0 0 520 440"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={styles.svg}
        role="img"
        aria-label="Connected healthcare network — Hospital, CMS/Admin, Patient, Records and Data nodes linked to a central CTS Healthcare hub"
      >
        {/* ── Ambient background rings ── */}
        <circle cx="260" cy="220" r="185" fill={C_BG_RING1} opacity="0.55"/>
        <circle cx="260" cy="220" r="128" fill={C_BG_RING2} opacity="0.45"/>
        <circle cx="260" cy="220" r="72"  fill={C_BG_RING2} opacity="0.35"/>

        {/* ── Connection lines (hub → each node) ── */}
        {nodes.map(n => (
          <line
            key={`line-${n.label}`}
            x1="260" y1="220"
            x2={n.cx} y2={n.cy}
            stroke={C_LINE}
            strokeWidth="1.5"
            strokeDasharray="6 4"
            opacity="0.45"
          />
        ))}

        {/* ── Satellite nodes ── */}
        {nodes.map(n => (
          <g key={`node-${n.label}`}>
            {/* Outer glow ring */}
            <circle cx={n.cx} cy={n.cy} r={n.r + 8} fill={C_PRIMARY} opacity="0.05"/>
            {/* White circle */}
            <circle cx={n.cx} cy={n.cy} r={n.r} fill={C_NODE_BG} stroke={C_NODE_STR} strokeWidth="1.5"/>
            {/* Icon — each drawn relative to node centre */}
            <NodeIcon type={n.icon} cx={n.cx} cy={n.cy} r={n.r} color={C_ICON} teal={C_TEAL}/>
            {/* Label */}
            <text
              x={n.cx}
              y={n.cy + n.r + 14}
              textAnchor="middle"
              fontSize="10"
              fontWeight="600"
              fontFamily="Inter, Arial, sans-serif"
              fill={C_PRIMARY}
              opacity="0.85"
            >
              {n.label}
            </text>
          </g>
        ))}

        {/* ── Central hub ── */}
        <circle cx="260" cy="220" r="58" fill={C_PRIMARY} opacity="0.1"/>
        <circle cx="260" cy="220" r="46" fill={C_PRIMARY}/>
        {/* Plus / cross — perfectly centred */}
        <rect x="254" y="204" width="12" height="32" rx="3" fill="white" opacity="0.95"/>
        <rect x="244" y="214" width="32" height="12" rx="3" fill="white" opacity="0.95"/>
        {/* Brand label */}
        <text
          x="260" y="278"
          textAnchor="middle"
          fontSize="9"
          fontWeight="700"
          fontFamily="Inter, Arial, sans-serif"
          fill={C_PRIMARY}
          opacity="0.6"
          letterSpacing="0.5"
        >
          CTS Healthcare
        </text>

        {/* ── Dot grid (decorative) ── */}
        {[60,130,200,260,320,390,460].map(x =>
          [40,100,160,220,280,340,400].map(y => (
            <circle key={`d-${x}-${y}`} cx={x} cy={y} r="1.5" fill={C_PRIMARY} opacity="0.035"/>
          ))
        )}
      </svg>
    </div>
  )
}

/* ──────────────────────────────────────────────────────────────────
   NodeIcon — renders the correct icon centred at (cx, cy).
   All paths are defined so that (0,0) is the icon's centre, then
   translated via a <g transform="translate(cx,cy)">. This guarantees
   perfect centering regardless of node radius.
────────────────────────────────────────────────────────────────── */
function NodeIcon({ type, cx, cy, color, teal }) {
  const s = 1.35  // uniform scale — increase to make icons larger

  const icons = {
    /* Hospital — building with H cross on facade */
    hospital: (
      <g>
        {/* Main building body */}
        <rect x={-9*s} y={-4*s} width={18*s} height={13*s} rx={1.5*s} stroke={color} strokeWidth={1.4} fill="none"/>
        {/* Roof / pediment */}
        <rect x={-7*s} y={-8*s} width={14*s} height={5*s}  rx={1*s}   stroke={color} strokeWidth={1.4} fill="none"/>
        {/* Cross on building — vertical */}
        <rect x={-1.2*s} y={-6*s} width={2.4*s} height={8*s}  rx={0.6*s} fill={teal}/>
        {/* Cross on building — horizontal */}
        <rect x={-4*s}   y={-3.2*s} width={8*s}   height={2.4*s} rx={0.6*s} fill={teal}/>
        {/* Door */}
        <rect x={-2.5*s} y={4*s} width={5*s} height={5*s} rx={0.8*s} stroke={color} strokeWidth={1.2} fill="none"/>
      </g>
    ),

    /* Admin / CMS — monitor with menu lines */
    admin: (
      <g>
        {/* Monitor screen */}
        <rect x={-11*s} y={-8*s} width={22*s} height={15*s} rx={2*s} stroke={color} strokeWidth={1.4} fill="none"/>
        {/* Stand stem */}
        <rect x={-1*s} y={7*s} width={2*s} height={4*s} rx={0.5*s} fill={color} opacity="0.6"/>
        {/* Stand base */}
        <rect x={-5*s} y={10.5*s} width={10*s} height={2*s} rx={1*s} fill={color} opacity="0.5"/>
        {/* Menu lines inside screen */}
        <rect x={-7*s} y={-4.5*s} width={9*s}  height={1.8*s} rx={0.7*s} fill={teal} opacity="0.8"/>
        <rect x={-7*s} y={-0.8*s} width={14*s} height={1.8*s} rx={0.7*s} fill={teal} opacity="0.6"/>
        <rect x={-7*s} y={2.9*s}  width={11*s} height={1.8*s} rx={0.7*s} fill={teal} opacity="0.5"/>
      </g>
    ),

    /* Patient — person silhouette */
    patient: (
      <g>
        {/* Head */}
        <circle cx="0" cy={-7*s} r={4.5*s} stroke={color} strokeWidth={1.4} fill="none"/>
        {/* Shoulders arc */}
        <path
          d={`M ${-9*s} ${8*s} C ${-9*s} ${1*s} ${9*s} ${1*s} ${9*s} ${8*s}`}
          stroke={color} strokeWidth={1.4} fill="none" strokeLinecap="round"
        />
      </g>
    ),

    /* Records — document with lines */
    records: (
      <g>
        {/* Document body */}
        <rect x={-8*s} y={-10*s} width={16*s} height={20*s} rx={2*s} stroke={color} strokeWidth={1.4} fill="none"/>
        {/* Folded corner */}
        <path d={`M ${4*s} ${-10*s} L ${8*s} ${-6*s} L ${4*s} ${-6*s} Z`} fill={teal} opacity="0.4"/>
        {/* Text lines */}
        <rect x={-5*s} y={-3*s}  width={10*s} height={1.8*s} rx={0.7*s} fill={teal} opacity="0.7"/>
        <rect x={-5*s} y={0.5*s} width={8*s}  height={1.8*s} rx={0.7*s} fill={teal} opacity="0.55"/>
        <rect x={-5*s} y={4*s}   width={6*s}  height={1.8*s} rx={0.7*s} fill={teal} opacity="0.4"/>
      </g>
    ),

    /* Data — stacked cylinders / database */
    data: (
      <g>
        {/* Top ellipse */}
        <ellipse cx="0" cy={-7*s} rx={7.5*s} ry={2.5*s} stroke={color} strokeWidth={1.3} fill="none"/>
        {/* Side walls */}
        <line x1={-7.5*s} y1={-7*s} x2={-7.5*s} y2={6*s} stroke={color} strokeWidth={1.3}/>
        <line x1={ 7.5*s} y1={-7*s} x2={ 7.5*s} y2={6*s} stroke={color} strokeWidth={1.3}/>
        {/* Bottom ellipse */}
        <ellipse cx="0" cy={6*s}  rx={7.5*s} ry={2.5*s} stroke={color} strokeWidth={1.3} fill="none"/>
        {/* Middle divider */}
        <path d={`M ${-7.5*s} ${-0.5*s} Q 0 ${2.5*s} ${7.5*s} ${-0.5*s}`} stroke={teal} strokeWidth={1.2} fill="none" opacity="0.6"/>
      </g>
    ),
  }

  const icon = icons[type]
  if (!icon) return null

  return (
    <g transform={`translate(${cx}, ${cy})`} aria-hidden="true">
      {icon}
    </g>
  )
}
