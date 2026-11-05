/* Collaboration map + co-author network (needs d3 v7 and topojson-client). */
(function () {
  const dataEl = document.getElementById('collab-data');
  if (!dataEl || !window.d3) return;
  const DATA = JSON.parse(dataEl.textContent);
  const SELF = 'Florenc Demrozi';
  const HOME = { name: 'University of Stavanger', lat: 58.938, lon: 5.694 };
  const WORLD_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';

  // Scopus/OpenAlex country names -> world-atlas names
  const ALIAS = {
    'United States': 'United States of America', 'USA': 'United States of America',
    'The Netherlands': 'Netherlands', 'Czech Republic': 'Czechia',
    'Russian Federation': 'Russia', 'Korea, Republic of': 'South Korea', 'Republic of Korea': 'South Korea',
    'Viet Nam': 'Vietnam', 'Bosnia and Herzegovina': 'Bosnia and Herz.',
    'Dominican Republic': 'Dominican Rep.', 'Hong Kong': 'China', 'Macao': 'China',
    'Iran, Islamic Republic of': 'Iran', 'Türkiye': 'Turkey', 'North Macedonia': 'Macedonia',
    'Côte d\'Ivoire': 'Côte d\'Ivoire', 'United Republic of Tanzania': 'Tanzania'
  };
  const mapName = n => ALIAS[n] || n;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const listNames = (arr, max) => {
    const shown = arr.slice(0, max).map(esc).join(', ');
    return arr.length > max ? `${shown} <em>and ${arr.length - max} more</em>` : shown;
  };

  // shared tooltip
  const tip = document.createElement('div');
  tip.className = 'collab-tip';
  document.body.appendChild(tip);
  const showTip = (html, ev) => {
    tip.innerHTML = html; tip.style.opacity = 1;
    const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = ev.clientY - h - pad;
    tip.style.left = Math.max(8, x) + 'px'; tip.style.top = Math.max(8, y) + 'px';
  };
  const hideTip = () => { tip.style.opacity = 0; };

  const byCountry = {};
  DATA.coauthors.forEach(c => { if (c.country) (byCountry[c.country] = byCountry[c.country] || []).push(c.name); });
  const countryInfo = {};
  DATA.countries.forEach(c => { countryInfo[mapName(c.name)] = c; });

  // ── MAP ──────────────────────────────────────────────────────
  document.querySelectorAll('.collab-map').forEach(el => {
    const compact = el.dataset.compact === 'true';
    fetch(WORLD_URL).then(r => r.json()).then(world => {
      const countries = topojson.feature(world, world.objects.countries).features
        .filter(f => f.properties.name !== 'Antarctica');
      // frame on the band of the world that holds the partners (lon/lat box from the data)
      const pts = DATA.institutions.filter(i => i.lat != null).map(i => [i.lon, i.lat]).concat([[HOME.lon, HOME.lat]]);
      const lons = pts.map(p => p[0]), lats = pts.map(p => p[1]);
      // full longitude range, latitude band around the partners (edges sampled so curved bounds are right)
      const latLo = Math.max(-58, Math.min(5, d3.min(lats) - 20)), latHi = Math.min(80, d3.max(lats) + 14);
      const edge = [];
      for (let lo = -180; lo <= 180; lo += 10) edge.push([lo, latLo], [lo, latHi]);
      for (let la = latLo; la <= latHi; la += 5) edge.push([-180, la], [180, la]);
      const box = { type: 'Feature', geometry: { type: 'MultiPoint', coordinates: edge } };
      const W = 960;
      const proj = d3.geoNaturalEarth1().fitWidth(W, box);
      const path = d3.geoPath(proj);
      const [[, y0], [, y1]] = path.bounds(box);
      const H = Math.max(260, Math.round(y1 - y0));
      proj.translate([proj.translate()[0], proj.translate()[1] - y0]);
      const max = d3.max(DATA.countries, d => d.papers) || 1;
      const color = d3.scaleSequentialLog([1, max], t => d3.interpolateRgb('#f3d2cc', '#8e2a1f')(t));

      const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img')
        .attr('aria-label', `Map of ${DATA.countries.length} collaborating countries`);
      const g = svg.append('g');

      g.selectAll('path').data(countries).join('path')
        .attr('d', path)
        .attr('class', d => 'collab-country' + (countryInfo[d.properties.name] ? ' is-partner' : ''))
        .style('fill', d => { const c = countryInfo[d.properties.name]; return c ? color(c.papers) : null; })
        .on('mousemove', (ev, d) => {
          const c = countryInfo[d.properties.name];
          if (!c) return hideTip();
          const people = byCountry[c.name] || [];
          showTip(`<strong>${esc(c.name)}</strong><span>${c.papers} joint paper${c.papers > 1 ? 's' : ''} · ${c.people} collaborator${c.people > 1 ? 's' : ''}</span>` +
            (people.length ? `<p>${listNames(people, 10)}</p>` : ''), ev);
        })
        .on('mouseleave', hideTip);

      // home (Stavanger)
      const [hx, hy] = proj([HOME.lon, HOME.lat]);
      const inst = DATA.institutions.filter(i => i.lat != null && i.lon != null);
      if (!compact) {
        g.append('g').selectAll('path').data(inst).join('path')
          .attr('class', 'collab-arc')
          .attr('d', d => {
            const [x, y] = proj([d.lon, d.lat]);
            const mx = (hx + x) / 2, my = (hy + y) / 2 - Math.hypot(x - hx, y - hy) * 0.25;
            return `M${hx},${hy} Q${mx},${my} ${x},${y}`;
          });
      }
      const r = d3.scaleSqrt([1, d3.max(inst, d => d.papers) || 1], compact ? [2.5, 8] : [3, 13]);
      g.append('g').selectAll('circle').data(inst.slice().sort((a, b) => b.papers - a.papers)).join('circle')
        .attr('class', 'collab-inst')
        .attr('cx', d => proj([d.lon, d.lat])[0]).attr('cy', d => proj([d.lon, d.lat])[1])
        .attr('r', d => r(d.papers))
        .on('mousemove', (ev, d) => showTip(`<strong>${esc(d.name)}</strong><span>${esc([d.city, d.country].filter(Boolean).join(', '))} · ${d.papers} joint paper${d.papers > 1 ? 's' : ''}</span>` +
          (d.people.length ? `<p>${listNames(d.people, 12)}</p>` : ''), ev))
        .on('mouseleave', hideTip);
      g.append('circle').attr('class', 'collab-home').attr('cx', hx).attr('cy', hy).attr('r', compact ? 4 : 6)
        .on('mousemove', ev => showTip(`<strong>${HOME.name}</strong><span>Home institution · Stavanger, Norway</span>`, ev))
        .on('mouseleave', hideTip);

      if (!compact) {
        const zoom = d3.zoom().scaleExtent([1, 8]).translateExtent([[0, 0], [W, H]])
          .on('zoom', ev => {
            const k = ev.transform.k, f = Math.pow(k, 0.75);
            g.attr('transform', ev.transform);
            g.selectAll('circle.collab-inst').attr('r', d => r(d.papers) / f).attr('stroke-width', 1 / k);
            g.selectAll('circle.collab-home').attr('r', 6 / f).attr('stroke-width', 2 / k);
          });
        svg.call(zoom).on('wheel.zoom', null);
        const ctr = d3.select(el).append('div').attr('class', 'collab-zoom');
        ctr.append('button').attr('type', 'button').attr('aria-label', 'Zoom in').text('+').on('click', () => svg.transition().call(zoom.scaleBy, 1.6));
        ctr.append('button').attr('type', 'button').attr('aria-label', 'Zoom out').text('−').on('click', () => svg.transition().call(zoom.scaleBy, 1 / 1.6));
        ctr.append('button').attr('type', 'button').attr('aria-label', 'Reset map').text('⟲').on('click', () => svg.transition().call(zoom.transform, d3.zoomIdentity));
        // quick jump to Europe, where most partners are
        const [ex0, ey0] = proj([-11, 66]), [ex1, ey1] = proj([30, 35]);
        const k = Math.min(8, 0.8 / Math.max((ex1 - ex0) / W, (ey1 - ey0) / H));
        const eu = d3.zoomIdentity.translate(W / 2, H / 2).scale(k).translate(-(ex0 + ex1) / 2, -(ey0 + ey1) / 2);
        d3.select(el).append('div').attr('class', 'collab-region')
          .selectAll('button').data([['World', d3.zoomIdentity], ['Europe', eu]]).join('button')
          .attr('type', 'button').text(d => d[0])
          .on('click', (ev, d) => svg.transition().duration(600).call(zoom.transform, d[1]));
      }
    }).catch(() => { el.innerHTML = '<p class="collab-error">The map could not be loaded.</p>'; });
  });

  // ── NETWORK ──────────────────────────────────────────────────
  const netEl = document.getElementById('collab-network');
  if (netEl) {
    const topCountries = DATA.countries.slice(0, 6).map(c => c.name);
    const palette = ['#2d5d9f', '#c0392b', '#b8860b', '#2e7d5b', '#6a4c93', '#2a8c9c'];
    const OTHER = '#9aa0a6';
    const colorOf = c => { const i = topCountries.indexOf(c); return i >= 0 ? palette[i] : OTHER; };

    const nodes = [{ id: '__self', name: SELF, institution: HOME.name, country: 'Norway', papers: DATA.papers_counted, self: true }]
      .concat(DATA.coauthors.map(c => ({ ...c })));
    const ids = new Set(nodes.map(n => n.id));
    const links = DATA.coauthors.map(c => ({ source: '__self', target: c.id, weight: c.papers, spoke: true }))
      .concat(DATA.links.filter(l => ids.has(l.source) && ids.has(l.target)).map(l => ({ ...l })));
    const adj = new Map(nodes.map(n => [n.id, new Set([n.id])]));
    links.forEach(l => { adj.get(l.source).add(l.target); adj.get(l.target).add(l.source); });

    const W = 960, H = 640;
    const svg = d3.select(netEl).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img')
      .attr('aria-label', `Co-author network with ${DATA.coauthors.length} collaborators`);
    const g = svg.append('g');
    const rad = d => d.self ? 16 : 3 + Math.sqrt(d.papers) * 2.6;

    const link = g.append('g').selectAll('line').data(links).join('line')
      .attr('class', d => 'net-link' + (d.spoke ? ' spoke' : ''))
      .attr('stroke-width', d => Math.min(4, 0.6 + Math.log2(d.weight + 1) * 0.7));
    const node = g.append('g').selectAll('circle').data(nodes).join('circle')
      .attr('class', d => 'net-node' + (d.self ? ' self' : ''))
      .attr('r', rad)
      .attr('fill', d => d.self ? '#1a1a2e' : colorOf(d.country));
    const label = g.append('g').selectAll('text').data(nodes.filter(d => d.self || d.papers >= 4)).join('text')
      .attr('class', d => 'net-label' + (d.self ? ' self' : ''))
      .text(d => d.name);

    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id)
        .distance(d => d.spoke ? 190 / Math.sqrt(d.weight) + 75 : 50)
        .strength(d => d.spoke ? 0.25 : 0.08))
      .force('charge', d3.forceManyBody().strength(d => d.self ? -600 : -60).distanceMax(320))
      .force('collide', d3.forceCollide(d => rad(d) + 2))
      .force('x', d3.forceX(W / 2).strength(0.05))
      .force('y', d3.forceY(H / 2).strength(0.09));
    nodes[0].fx = W / 2; nodes[0].fy = H / 2;

    sim.on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('cx', d => d.x).attr('cy', d => d.y);
      label.attr('x', d => d.x).attr('y', d => d.y - rad(d) - 4);
    });

    const focus = d => {
      const nb = adj.get(d.id);
      node.classed('dim', n => !nb.has(n.id));
      label.classed('dim', n => !nb.has(n.id));
      link.classed('dim', l => l.source.id !== d.id && l.target.id !== d.id)
        .classed('hot', l => l.source.id === d.id || l.target.id === d.id);
    };
    const unfocus = () => { node.classed('dim', false); label.classed('dim', false); link.classed('dim', false).classed('hot', false); };

    node.on('mousemove', (ev, d) => {
      focus(d);
      showTip(d.self
        ? `<strong>${esc(d.name)}</strong><span>${DATA.coauthors.length} co-authors · ${DATA.institutions.length} partner institutions</span>`
        : `<strong>${esc(d.name)}</strong><span>${esc(d.institution || '')}${d.country ? ', ' + esc(d.country) : ''}</span><p>${d.papers} joint paper${d.papers > 1 ? 's' : ''}</p>`, ev);
    }).on('mouseleave', () => { unfocus(); hideTip(); });

    node.call(d3.drag()
      .on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on('end', (ev, d) => { if (!ev.active) sim.alphaTarget(0); if (!d.self) { d.fx = null; d.fy = null; } }));

    const zoom = d3.zoom().scaleExtent([0.5, 5]).on('zoom', ev => g.attr('transform', ev.transform));
    svg.call(zoom).on('wheel.zoom', null);
    const ctr = d3.select(netEl).append('div').attr('class', 'collab-zoom');
    ctr.append('button').attr('type', 'button').attr('aria-label', 'Zoom in').text('+').on('click', () => svg.transition().call(zoom.scaleBy, 1.4));
    ctr.append('button').attr('type', 'button').attr('aria-label', 'Zoom out').text('−').on('click', () => svg.transition().call(zoom.scaleBy, 1 / 1.4));
    ctr.append('button').attr('type', 'button').attr('aria-label', 'Reset view').text('⟲').on('click', () => svg.transition().call(zoom.transform, d3.zoomIdentity));

    // legend
    const legend = document.getElementById('collab-network-legend');
    if (legend) {
      const others = DATA.countries.length > topCountries.length;
      legend.innerHTML = topCountries.map((c, i) => `<span><i style="background:${palette[i]}"></i>${esc(c)}</span>`).join('') +
        (others ? `<span><i style="background:${OTHER}"></i>Other countries</span>` : '');
    }

    // search
    const search = document.getElementById('collab-search');
    if (search) {
      search.addEventListener('input', () => {
        const q = search.value.trim().toLowerCase();
        if (!q) return unfocus();
        const hit = nodes.find(n => n.name.toLowerCase().includes(q));
        if (hit) focus(hit);
      });
    }
  }

  // ── "show all" toggles ───────────────────────────────────────
  document.querySelectorAll('[data-collab-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const list = document.getElementById(btn.dataset.collabToggle);
      const open = list.classList.toggle('show-all');
      btn.textContent = open ? 'Show fewer' : btn.dataset.label;
    });
  });
})();
