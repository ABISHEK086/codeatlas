import { useEffect, useMemo, useRef, useState } from 'react'
import {
  forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation,
  type SimulationLinkDatum, type SimulationNodeDatum,
} from 'd3-force'
import { api, type GraphData, type Repo } from '@/api'

type SimNode = SimulationNodeDatum & { id: number; path: string; kind: string }

const KIND_COLOR: Record<string, string> = {
  source: '#2f81f7',
  test: '#3fb950',
  config: '#8b949e',
  doc: '#8b949e',
}

export default function GraphPage({ repo }: { repo: Repo }) {
  const [data, setData] = useState<GraphData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)

  useEffect(() => {
    let live = true
    api.graph(repo.id)
      .then((d) => { if (live) setData(d) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load graph') })
    return () => { live = false }
  }, [repo.id])

  // Layout runs once per graph, synchronously, so the picture is stable (no jitter).
  const layout = useMemo(() => {
    if (!data) return null
    const connected = new Set<number>()
    for (const e of data.edges) { connected.add(e.source); connected.add(e.target) }
    const nodes: SimNode[] = data.nodes
      .filter((n) => connected.has(n.id))
      .map((n) => ({ id: n.id, path: n.path, kind: n.kind }))
    const links: SimulationLinkDatum<SimNode>[] = data.edges.map((e) => ({ source: e.source, target: e.target }))
    const sim = forceSimulation(nodes)
      .force('link', forceLink<SimNode, SimulationLinkDatum<SimNode>>(links).id((d) => d.id).distance(42).strength(0.6))
      .force('charge', forceManyBody().strength(-140))
      .force('center', forceCenter(0, 0))
      .force('collide', forceCollide(9))
      .stop()
    for (let i = 0; i < 320; i++) sim.tick()
    return {
      nodes,
      links: links.map((l) => ({ s: l.source as SimNode, t: l.target as SimNode })),
    }
  }, [data])

  // Everything that depends on the selected file, directly or indirectly.
  const blast = useMemo(() => {
    if (selected === null || !data) return null
    const importers = new Map<number, number[]>()
    for (const e of data.edges) {
      const list = importers.get(e.target) ?? []
      list.push(e.source)
      importers.set(e.target, list)
    }
    const seen = new Set<number>()
    const stack = [selected]
    while (stack.length) {
      const cur = stack.pop()!
      for (const s of importers.get(cur) ?? []) {
        if (s !== selected && !seen.has(s)) { seen.add(s); stack.push(s) }
      }
    }
    return seen
  }, [selected, data])

  // Wheel zoom needs a non-passive listener to stop the page scrolling.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const f = e.deltaY < 0 ? 1.12 : 1 / 1.12
      setView((v) => ({ ...v, k: Math.min(4, Math.max(0.3, v.k * f)) }))
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [layout])

  const onPointerDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current
    const svg = svgRef.current
    if (!d || !svg) return
    const unit = 900 / svg.clientWidth
    setView((v) => ({ ...v, x: d.vx + (e.clientX - d.x) * unit, y: d.vy + (e.clientY - d.y) * unit }))
  }
  const onPointerUp = () => { drag.current = null }

  const byId = useMemo(() => new Map(layout?.nodes.map((n) => [n.id, n])), [layout])
  const dependents = blast ? [...blast].map((id) => byId.get(id)?.path).filter(Boolean) as string[] : []
  const label = hover ?? selected

  if (error) return <p className="p-8 text-sm text-danger">{error}</p>
  if (!layout) return <div className="m-8 h-[520px] animate-pulse rounded-md border border-border bg-card" />

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 py-8 sm:px-8">
      <h1 className="mb-1 text-xl font-semibold">Dependency graph</h1>
      <p className="mb-4 text-sm text-muted-foreground">
        {layout.nodes.length} connected files, {layout.links.length} import links. Click a file to see everything that depends on it.
      </p>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="relative overflow-hidden rounded-md border border-border bg-card">
          <svg
            ref={svgRef}
            viewBox="-450 -300 900 600"
            className="h-[560px] w-full cursor-grab touch-none select-none active:cursor-grabbing"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
          >
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              {layout.links.map((l, i) => {
                const hot = blast && (blast.has(l.s.id) && (blast.has(l.t.id) || l.t.id === selected))
                return (
                  <line
                    key={i}
                    x1={l.s.x} y1={l.s.y} x2={l.t.x} y2={l.t.y}
                    stroke={hot ? '#f85149' : '#30363d'}
                    strokeOpacity={blast && !hot ? 0.25 : 1}
                    strokeWidth={hot ? 1.5 : 1}
                  />
                )
              })}
              {layout.nodes.map((n) => {
                const isSel = n.id === selected
                const hot = blast?.has(n.id)
                const dim = blast !== null && !isSel && !hot
                return (
                  <circle
                    key={n.id}
                    cx={n.x} cy={n.y}
                    r={isSel ? 8 : 5}
                    fill={hot ? '#f85149' : KIND_COLOR[n.kind] ?? '#8b949e'}
                    stroke={isSel ? '#e6edf3' : 'none'}
                    strokeWidth={2}
                    opacity={dim ? 0.2 : 1}
                    className="cursor-pointer"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={() => setSelected(isSel ? null : n.id)}
                    onMouseEnter={() => setHover(n.id)}
                    onMouseLeave={() => setHover(null)}
                  />
                )
              })}
            </g>
          </svg>

          <div className="pointer-events-none absolute bottom-0 left-0 right-0 truncate border-t border-border bg-card/90 px-3 py-1.5 font-mono text-xs text-muted-foreground">
            {label !== null ? byId.get(label)?.path : 'Hover a node for its path'}
          </div>

          <div className="absolute right-3 top-3 flex flex-col overflow-hidden rounded-md border border-border bg-card text-sm">
            <button className="px-2.5 py-1 hover:bg-muted" onClick={() => setView((v) => ({ ...v, k: Math.min(4, v.k * 1.25) }))}>+</button>
            <button className="border-t border-border px-2.5 py-1 hover:bg-muted" onClick={() => setView((v) => ({ ...v, k: Math.max(0.3, v.k / 1.25) }))}>−</button>
            <button className="border-t border-border px-2.5 py-1 text-xs hover:bg-muted" onClick={() => setView({ x: 0, y: 0, k: 1 })}>⟲</button>
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-md border border-border bg-card p-4 text-xs">
            <p className="mb-2 font-semibold text-foreground">Legend</p>
            {[['Source', '#2f81f7'], ['Test', '#3fb950'], ['Would break', '#f85149']].map(([name, color]) => (
              <p key={name} className="flex items-center gap-2 py-0.5 text-muted-foreground">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />{name}
              </p>
            ))}
          </div>

          <div className="rounded-md border border-border bg-card p-4">
            {selected === null ? (
              <p className="text-xs text-muted-foreground">Select a file to see its blast radius.</p>
            ) : (
              <>
                <p className="truncate font-mono text-xs">{byId.get(selected)?.path}</p>
                <p className="mb-2 mt-1 text-sm">
                  <span className="font-semibold text-danger">{dependents.length}</span>{' '}
                  <span className="text-muted-foreground">file(s) could break</span>
                </p>
                <ul className="max-h-64 space-y-0.5 overflow-y-auto">
                  {dependents.map((p) => (
                    <li key={p} className="truncate font-mono text-[11px] text-muted-foreground">{p}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}