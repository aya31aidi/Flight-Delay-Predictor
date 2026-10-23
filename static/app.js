(() => {
  const ref = JSON.parse(document.getElementById("reference").textContent);
  const form = document.getElementById("flight-form");
  const output = document.getElementById("output");
  const $ = (sel, root = document) => root.querySelector(sel);

  const pct = (x) => `${Math.round(x * 100)}%`;
  const fmt = (n) => n.toLocaleString("en-US");
  const shortName = (name) => name.replace(/ (Inc\.|Co\.|Corporation)$/, "").replace(/ (Air Lines|Airlines)$/, "");

  /* ---------- Thème clair / sombre ---------- */
  $(".theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const isDark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = isDark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
  });

  /* ---------- Route : destinations, historique, valeurs typiques ---------- */
  const dest = form.elements.dest;
  const carrier = form.elements.carrier;
  const routeInfo = $("#route-info");
  const allDestinations = [...dest.options].slice(1);

  const origin = () => form.elements.origin.value;
  const currentRoute = () => (ref.routes[origin()] || {})[dest.value];

  function filterDestinations() {
    const served = ref.routes[origin()] || {};
    const previous = dest.value;
    dest.replaceChildren(dest.options[0], ...allDestinations.filter((o) => o.value in served));
    dest.value = previous in served ? previous : "";
  }

  function showRouteInfo() {
    const route = currentRoute();
    form.elements.air_time.placeholder = route ? `Typical: ${route.air_time} min` : "Estimated from distance";
    form.elements.distance.placeholder = route ? `${fmt(route.distance)} mi for this route` : "Required for unknown routes";

    if (!route) {
      routeInfo.hidden = true;
      return;
    }
    const flownBy = route.carriers.includes(carrier.value) || !carrier.value;
    routeInfo.classList.toggle("is-warning", !flownBy);
    routeInfo.innerHTML = `
      <span><b>${fmt(route.flights)}</b> flights in 2013</span>
      <span><b>${pct(route.delay_rate)}</b> arrived late</span>
      <span><b>${fmt(route.distance)}</b> miles</span>
      <span>Flown by <b>${route.carriers.join(", ")}</b></span>
      ${flownBy ? "" : `<span>${shortName(ref.airlines[carrier.value])} did not fly this route in 2013.</span>`}`;
    routeInfo.hidden = false;
  }

  /* ---------- Retard au départ calculé en direct ---------- */
  const readout = $("#delay-readout");
  const readoutDefault = readout.textContent;

  function showDepartureDelay() {
    const [sched, actual] = [form.elements.sched_dep_time.value, form.elements.dep_time.value];
    readout.classList.remove("is-late", "is-early");
    if (!sched || !actual) {
      readout.textContent = readoutDefault;
      return;
    }
    const minutes = (t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
    let gap = minutes(actual) - minutes(sched);
    if (gap < -720) gap += 1440;
    if (gap > 720) gap -= 1440;

    if (gap === 0) readout.textContent = "Left right on time.";
    else if (gap > 0) readout.textContent = `Left ${gap} min late.`;
    else readout.textContent = `Left ${-gap} min early.`;
    readout.classList.add(gap > 0 ? "is-late" : "is-early");
  }

  form.elements.origin.forEach((radio) => radio.addEventListener("change", () => { filterDestinations(); showRouteInfo(); }));
  dest.addEventListener("change", showRouteInfo);
  carrier.addEventListener("change", showRouteInfo);
  form.elements.sched_dep_time.addEventListener("input", showDepartureDelay);
  form.elements.dep_time.addEventListener("input", showDepartureDelay);

  if (!form.elements.date.value) form.elements.date.value = new Date().toISOString().slice(0, 10);
  filterDestinations();
  showRouteInfo();
  showDepartureDelay();

  /* ---------- Exemples ---------- */
  const examples = {
    plan: { origin: "JFK", dest: "LAX", carrier: "AA", flight: "33", date: "2013-07-27", sched_dep_time: "15:30", sched_arr_time: "18:50" },
    late: { origin: "EWR", dest: "ORD", carrier: "UA", flight: "1120", date: "2013-12-20", sched_dep_time: "18:00", sched_arr_time: "19:35", dep_time: "19:10" },
    close: { origin: "LGA", dest: "ATL", carrier: "DL", flight: "1947", date: "2013-06-14", sched_dep_time: "16:00", sched_arr_time: "18:20", dep_time: "16:12" },
  };

  document.querySelectorAll("[data-example]").forEach((button) => {
    button.addEventListener("click", () => {
      const values = examples[button.dataset.example];
      clearErrors();
      for (const field of ["flight", "dep_time", "arr_time", "air_time", "distance"]) form.elements[field].value = "";
      form.elements.origin.value = values.origin;
      filterDestinations();
      for (const [name, val] of Object.entries(values)) {
        if (name !== "origin") form.elements[name].value = val;
      }
      showRouteInfo();
      showDepartureDelay();
      form.requestSubmit();
    });
  });

  /* ---------- Envoi sans rechargement de la page ---------- */
  function clearErrors() {
    form.querySelectorAll("[data-error-for]").forEach((p) => { p.textContent = ""; });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors();
    form.classList.add("is-loading");
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch" },
      });
      if (response.status === 422) {
        const { errors } = await response.json();
        for (const [name, message] of Object.entries(errors)) {
          const slot = form.querySelector(`[data-error-for="${name}"]`);
          if (slot) slot.textContent = message;
        }
        form.querySelector(".field__error:not(:empty)")?.closest(".field")?.querySelector("input, select")?.focus();
        return;
      }
      if (!response.ok) throw new Error(response.statusText);

      output.innerHTML = await response.text();
      const result = $(".result", output);
      result.focus({ preventScroll: true });
      if (output.getBoundingClientRect().top > innerHeight || matchMedia("(max-width: 960px)").matches) {
        output.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      // Si le serveur ne répond pas comme prévu, envoi classique du formulaire
      form.submit();
    } finally {
      form.classList.remove("is-loading");
    }
  });

  form.addEventListener("reset", () => {
    clearErrors();
    setTimeout(() => {
      form.elements.date.value = new Date().toISOString().slice(0, 10);
      filterDestinations();
      showRouteInfo();
      showDepartureDelay();
    });
  });

  /* ---------- Copier l'exemple d'API ---------- */
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(document.getElementById(button.dataset.copy).textContent);
        button.textContent = "Copied";
      } catch (e) {
        button.textContent = "Select and copy";
      }
      setTimeout(() => { button.textContent = "Copy"; }, 1600);
    });
  });

  /* ---------- Graphiques ---------- */
  const SVG = "http://www.w3.org/2000/svg";

  function el(name, attrs = {}, parent) {
    const node = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  function tooltipFor(container) {
    let tip = $(".tooltip", container);
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "tooltip";
      container.appendChild(tip);
    }
    return {
      show(x, y, html) {
        tip.innerHTML = html;
        const half = tip.offsetWidth / 2;
        tip.style.left = `${Math.min(Math.max(x, half), container.clientWidth - half)}px`;
        tip.style.top = `${y}px`;
        tip.classList.add("is-visible");
      },
      hide() { tip.classList.remove("is-visible"); },
    };
  }

  // Barre verticale avec coins arrondis en haut uniquement
  const columnPath = (x, y, w, h, r = 4) => {
    r = Math.min(r, h, w / 2);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  };
  // Barre horizontale arrondie à droite uniquement
  const barPath = (x, y, w, h, r = 4) => {
    r = Math.min(r, w, h / 2);
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  };

  function columnChart(container, data, { tickEvery = 1, describe }) {
    container.querySelector("svg")?.remove();
    const width = container.clientWidth;
    const height = 230;
    const m = { top: 22, right: 4, bottom: 26, left: 38 };
    const plotW = width - m.left - m.right;
    const plotH = height - m.top - m.bottom;
    const yMax = Math.ceil(Math.max(...data.map((d) => d.value)) * 10) / 10;
    const y = (v) => m.top + plotH * (1 - v / yMax);
    const band = plotW / data.length;
    const barW = Math.min(24, band * 0.64);

    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": container.dataset.label || "" });
    for (let t = 0; t <= yMax + 1e-9; t += 0.2) {
      el("line", { class: t === 0 ? "baseline" : "grid-line", x1: m.left, x2: width - m.right, y1: y(t), y2: y(t) }, svg);
      el("text", { class: "tick", x: m.left - 8, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = pct(t);
    }

    const values = data.map((d) => d.value);
    const highest = Math.max(...values);
    const lowest = Math.min(...values);
    const tip = tooltipFor(container);

    data.forEach((d, i) => {
      const cx = m.left + band * i + band / 2;
      const top = y(d.value);
      const mark = el("path", { class: "mark", d: columnPath(cx - barW / 2, top, barW, y(0) - top) }, svg);

      if (i % tickEvery === 0) {
        el("text", { class: "tick", x: cx, y: height - 8, "text-anchor": "middle" }, svg).textContent = d.label;
      }
      if (d.value === highest || d.value === lowest) {
        el("text", { class: `value${d.value === lowest ? " value--muted" : ""}`, x: cx, y: top - 7, "text-anchor": "middle" }, svg).textContent = pct(d.value);
      }

      const hit = el("rect", { class: "hit", x: cx - band / 2, y: m.top, width: band, height: plotH }, svg);
      hit.addEventListener("pointerenter", () => {
        mark.classList.add("is-active");
        tip.show(cx, top, describe(d));
      });
      hit.addEventListener("pointerleave", () => {
        mark.classList.remove("is-active");
        tip.hide();
      });
    });

    container.prepend(svg);
  }

  function barChart(container, data, average) {
    container.querySelector("svg")?.remove();
    const width = container.clientWidth;
    const narrow = width < 520;
    const row = 30;
    const m = { top: 26, right: 48, bottom: 4, left: narrow ? 120 : 190 };
    const height = m.top + data.length * row + m.bottom;
    const plotW = width - m.left - m.right;
    const xMax = Math.ceil(Math.max(...data.map((d) => d.value)) * 10) / 10;
    const x = (v) => m.left + plotW * (v / xMax);
    const barH = 16;

    const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Share of late arrivals by airline" });
    for (let t = 0; t <= xMax + 1e-9; t += 0.1) {
      el("line", { class: t === 0 ? "baseline" : "grid-line", x1: x(t), x2: x(t), y1: m.top - 6, y2: height - m.bottom }, svg);
      if (!narrow || Math.round(t * 10) % 2 === 0) {
        el("text", { class: "tick", x: x(t), y: 12, "text-anchor": "middle" }, svg).textContent = pct(t);
      }
    }

    const tip = tooltipFor(container);
    data.forEach((d, i) => {
      const top = m.top + i * row + (row - barH) / 2;
      el("text", { class: "tick", x: m.left - 10, y: top + barH - 4, "text-anchor": "end" }, svg).textContent = narrow ? d.code : d.label;
      const mark = el("path", { class: "mark", d: barPath(m.left, top, x(d.value) - m.left, barH) }, svg);
      el("text", { class: "value", x: x(d.value) + 6, y: top + barH - 4 }, svg).textContent = pct(d.value);

      const hit = el("rect", { class: "hit", x: 0, y: m.top + i * row, width, height: row }, svg);
      hit.addEventListener("pointerenter", () => {
        mark.classList.add("is-active");
        tip.show(x(d.value), top, `<b>${d.name}</b>${pct(d.value)} of flights arrived late`);
      });
      hit.addEventListener("pointerleave", () => { mark.classList.remove("is-active"); tip.hide(); });
    });

    // Repère : moyenne de tous les vols
    el("line", { class: "baseline", x1: x(average), x2: x(average), y1: m.top - 6, y2: height - m.bottom, "stroke-width": 2, style: "stroke: var(--ink-2)" }, svg);
    el("text", { class: "value value--muted", x: x(average) + 6, y: m.top - 8 }, svg).textContent = `All flights ${pct(average)}`;

    container.prepend(svg);
  }

  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

  function drawCharts() {
    const hourEl = $("#chart-hour");
    const hours = Object.entries(ref.stats.by_hour).map(([h, d]) => ({ label: `${h}h`, hour: +h, value: d.rate, flights: d.flights }));
    columnChart(hourEl, hours, {
      tickEvery: hourEl.clientWidth < 460 ? 3 : 2,
      describe: (d) => `<b>${d.hour}:00 – ${d.hour}:59</b>${pct(d.value)} late · ${fmt(d.flights)} flights`,
    });

    const monthEl = $("#chart-month");
    const narrow = monthEl.clientWidth < 420;
    const byMonth = ref.stats.by_month.map((v, i) => ({ label: narrow ? months[i][0] : months[i], name: monthNames[i], value: v }));
    columnChart(monthEl, byMonth, { describe: (d) => `<b>${d.name}</b>${pct(d.value)} of flights late` });

    const carriers = Object.entries(ref.stats.by_carrier)
      .map(([code, value]) => ({ code, value, name: ref.airlines[code], label: shortName(ref.airlines[code]) }))
      .sort((a, b) => b.value - a.value);
    barChart($("#chart-carrier"), carriers, ref.stats.delay_rate);
  }

  drawCharts();
  let resizeTimer;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawCharts, 120);
  }).observe($(".charts"));
})();
