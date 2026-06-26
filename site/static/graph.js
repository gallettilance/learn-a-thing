/**
 * Interactive concept graph — D3 force-directed layout.
 * Expects #concept-graph-mount, #graph-detail, #concept-graph-data (JSON).
 */
(function initConceptGraph() {
  const mount = document.getElementById("concept-graph-mount");
  const dataEl = document.getElementById("concept-graph-data");
  const detailEl = document.getElementById("graph-detail");
  if (!mount || !dataEl) return;

  const payload = JSON.parse(dataEl.textContent);
  const nodes = payload.nodes.map((n) => ({ ...n }));
  const links = payload.edges.map((e) => ({ ...e }));
  const invariants = payload.invariants || [];

  const EDGE_COLORS = {
    same_pressure: "#4a9eff",
    calibration_link: "#f59e0b",
    same_geometry: "#10b981",
    same_algebra: "#a78bfa",
    isomorphism: "#ec4899",
    generalizes: "#6366f1",
    limit_of: "#14b8a6",
  };

  const edgeTypes = [...new Set(links.map((l) => l.type))].sort();
  let activeTypes = new Set(edgeTypes);
  let selectedNode = null;
  let selectedLink = null;

  const toolbar = document.createElement("div");
  toolbar.className = "graph-toolbar";
  toolbar.innerHTML = `
    <div class="graph-filters">
      <span class="graph-toolbar-label">Edge types</span>
      <div class="graph-filter-chips" id="graph-filter-chips"></div>
    </div>
    <div class="graph-actions">
      <button type="button" class="graph-btn" id="graph-reset-view">Reset view</button>
    </div>`;
  const canvasWrap = mount.parentElement;
  if (canvasWrap) {
    canvasWrap.insertBefore(toolbar, mount);
  }

  const chips = toolbar.querySelector("#graph-filter-chips");
  edgeTypes.forEach((type) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "graph-chip active";
    chip.dataset.type = type;
    chip.style.setProperty("--chip-color", EDGE_COLORS[type] || "#888");
    chip.innerHTML = `<span class="chip-dot"></span>${type.replace(/_/g, " ")}`;
    chip.addEventListener("click", () => {
      if (activeTypes.has(type)) {
        activeTypes.delete(type);
        chip.classList.remove("active");
      } else {
        activeTypes.add(type);
        chip.classList.add("active");
      }
      if (activeTypes.size === 0) {
        activeTypes.add(type);
        chip.classList.add("active");
      }
      refreshLinks();
      updateVisibility();
    });
    chips.appendChild(chip);
  });

  function graphSize() {
    const w = Math.max(480, mount.clientWidth || canvasWrap?.clientWidth || 900);
    const vh = window.innerHeight || 800;
    const h = Math.max(520, Math.min(vh * 0.72, w * 0.68));
    return { w, h };
  }

  function setMountSize() {
    const { w, h } = graphSize();
    mount.style.height = `${h}px`;
    return { w, h };
  }

  let { w: initW, h: initH } = setMountSize();

  const svg = d3
    .select(mount)
    .append("svg")
    .attr("class", "concept-graph-svg")
    .attr("width", initW)
    .attr("height", initH)
    .attr("viewBox", [0, 0, initW, initH]);

  const gRoot = svg.append("g");
  const zoom = d3
    .zoom()
    .scaleExtent([0.25, 3])
    .on("zoom", (event) => gRoot.attr("transform", event.transform));
  svg.call(zoom);

  const linkG = gRoot.append("g").attr("class", "links");
  const nodeG = gRoot.append("g").attr("class", "nodes");

  const simulation = d3
    .forceSimulation(nodes)
    .force(
      "link",
      d3
        .forceLink(links)
        .id((d) => d.id)
        .distance(140)
        .strength(0.55)
    )
    .force("charge", d3.forceManyBody().strength(-420))
    .force("center", d3.forceCenter(initW / 2, initH / 2))
    .force("collide", d3.forceCollide().radius(42));

  function applySize() {
    const { w, h } = setMountSize();
    svg.attr("width", w).attr("height", h).attr("viewBox", [0, 0, w, h]);
    simulation.force("center", d3.forceCenter(w / 2, h / 2));
  }

  function linkKey(l) {
    return l.id || `${l.source.id || l.source}-${l.target.id || l.target}`;
  }

  function visibleLinks() {
    return links.filter((l) => activeTypes.has(l.type));
  }

  function neighborSet(nodeId) {
    const n = new Set([nodeId]);
    visibleLinks().forEach((l) => {
      const s = l.source.id || l.source;
      const t = l.target.id || l.target;
      if (s === nodeId) n.add(t);
      if (t === nodeId) n.add(s);
    });
    return n;
  }

  function renderDetailNode(node) {
    if (!detailEl) return;
    const invs = invariants.filter((i) => (i.topics || []).includes(node.label));
    const invHtml = invs.length
      ? `<ul>${invs.map((i) => `<li><strong>${esc(i.name)}</strong> — ${esc(i.statement)}</li>`).join("")}</ul>`
      : "<p class='meta'>No invariant cluster assigned.</p>";
    const lessonLink = node.slug
      ? `<p><a href="/topics/${node.slug}.html">View lessons in ${esc(node.label)} →</a></p>`
      : "";
    const masteredChecked = node.mastered ? " checked" : "";
    detailEl.innerHTML = `
      <h3>${esc(node.label)}</h3>
      <p class="meta">${node.lesson_count || 0} lesson${node.lesson_count === 1 ? "" : "s"} in catalog</p>
      ${lessonLink}
      <section class="topic-mastery-inline${node.mastered ? " is-mastered" : ""}" data-topic="${esc(node.label)}">
        <label class="topic-mastery-label">
          <input type="checkbox" name="mastered"${masteredChecked} />
          <span class="topic-mastery-text">Already know this topic</span>
        </label>
        <p class="hint topic-mastery-hint">Curator skips intro and bridge slots for mastered topics.</p>
        <p class="form-msg" hidden></p>
      </section>
      <h4>Pressure invariants</h4>
      ${invHtml}
      <p class="hint">Drag nodes · scroll to zoom · click an edge for mechanism detail.</p>`;
    window.bindTopicMastery?.(detailEl);
  }

  function renderDetailLink(link) {
    if (!detailEl) return;
    const src = link.source.label || link.source.id || link.source;
    const tgt = link.target.label || link.target.id || link.target;
    detailEl.innerHTML = `
      <h3><code>${esc(link.id)}</code></h3>
      <p><span class="badge edge-type" style="border-color:${EDGE_COLORS[link.type] || "#888"}">${esc(link.type.replace(/_/g, " "))}</span></p>
      <p class="graph-edge-route"><strong>${esc(src)}</strong> → <strong>${esc(tgt)}</strong></p>
      <p>${esc(link.statement || "")}</p>
      ${link.runtime ? "<p class='meta'>Runtime edge (grapher)</p>" : "<p class='meta'>Seed edge (curriculum)</p>"}`;
  }

  function renderDetailDefault() {
    if (!detailEl) return;
    detailEl.innerHTML = `
      <h3>Explore the graph</h3>
      <p class="hint">Topics are nodes; edges are mechanism links between tools and domains.</p>
      <p>Hover a node to highlight its neighborhood. Click a node or edge for details. Toggle edge types above to simplify the view.</p>`;
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let linkSel = linkG.selectAll("line").data(visibleLinks(), linkKey);
  let nodeSel = nodeG.selectAll("g.node").data(nodes, (d) => d.id);

  function refreshLinks() {
    computeDegrees();
    const vis = visibleLinks();
    simulation.force("link").links(vis);
    bindGraph();
    simulation.alpha(0.35).restart();
  }

  function computeDegrees() {
    nodes.forEach((n) => {
      n.degree = visibleLinks().filter((l) => {
        const s = typeof l.source === "object" ? l.source.id : l.source;
        const t = typeof l.target === "object" ? l.target.id : l.target;
        return s === n.id || t === n.id;
      }).length;
    });
  }

  function bindGraph() {
    linkSel = linkG.selectAll("line").data(visibleLinks(), linkKey);
    linkSel.exit().remove();
    const linkEnter = linkSel
      .enter()
      .append("line")
      .attr("class", "graph-link")
      .attr("stroke", (d) => EDGE_COLORS[d.type] || "#666")
      .attr("stroke-width", (d) => (d.runtime ? 2.5 : 2))
      .attr("stroke-dasharray", (d) => (d.runtime ? "6 3" : null))
      .on("click", (event, d) => {
        event.stopPropagation();
        selectedLink = d;
        selectedNode = null;
        renderDetailLink(d);
        updateVisibility();
      });
    linkSel = linkEnter.merge(linkSel);

    nodeSel = nodeG.selectAll("g.node").data(nodes, (d) => d.id);
    nodeSel.exit().remove();
    const nodeEnter = nodeSel
      .enter()
      .append("g")
      .attr("class", "node")
      .call(
        d3
          .drag()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      )
      .on("click", (event, d) => {
        event.stopPropagation();
        selectedNode = d;
        selectedLink = null;
        renderDetailNode(d);
        updateVisibility();
      })
      .on("mouseenter", (_, d) => {
        mount.dataset.hover = d.id;
        updateVisibility();
      })
      .on("mouseleave", () => {
        delete mount.dataset.hover;
        updateVisibility();
      });

    nodeEnter
      .append("circle")
      .attr("r", (d) => 10 + Math.min(8, (d.degree || 0) * 1.2))
      .attr("class", "node-circle");

    nodeEnter
      .append("text")
      .attr("class", "node-label")
      .attr("dy", 4)
      .attr("text-anchor", "middle")
      .text((d) => d.label);

    nodeSel = nodeEnter.merge(nodeSel);
  }

  computeDegrees();
  simulation.force("link").links(visibleLinks());
  bindGraph();
  renderDetailDefault();

  simulation.on("tick", () => {
    linkSel
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);

    nodeSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
  });

  function updateVisibility() {
    const hoverId = mount.dataset.hover;
    const focusId = selectedNode?.id || hoverId;
    const focusNeighbors = focusId ? neighborSet(focusId) : null;

    linkSel
      .classed("dimmed", (d) => {
        if (selectedLink && linkKey(d) !== linkKey(selectedLink)) return true;
        if (!focusId) return false;
        const s = d.source.id || d.source;
        const t = d.target.id || d.target;
        return !(s === focusId || t === focusId);
      })
      .classed("selected", (d) => selectedLink && linkKey(d) === linkKey(selectedLink));

    nodeSel.classed("dimmed", (d) => {
      if (selectedLink) {
        const s = selectedLink.source.id || selectedLink.source;
        const t = selectedLink.target.id || selectedLink.target;
        return d.id !== s && d.id !== t;
      }
      if (!focusId) return false;
      return !focusNeighbors.has(d.id);
    }).classed("selected", (d) => selectedNode && d.id === selectedNode.id);
  }

  svg.on("click", () => {
    selectedNode = null;
    selectedLink = null;
    renderDetailDefault();
    updateVisibility();
  });

  document.getElementById("graph-reset-view")?.addEventListener("click", () => {
    svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
    selectedNode = null;
    selectedLink = null;
    renderDetailDefault();
    updateVisibility();
  });

  window.addEventListener("resize", () => {
    applySize();
    simulation.alpha(0.3).restart();
  });

  if (typeof ResizeObserver !== "undefined" && canvasWrap) {
    const ro = new ResizeObserver(() => {
      applySize();
      simulation.alpha(0.15).restart();
    });
    ro.observe(canvasWrap);
  }
})();
