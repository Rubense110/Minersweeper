(function () {
  // Aseguramos que las variables globales existan
  if (!window.pcData || !window.pcLabels) {
    console.warn("Parallel coordinates: no data to display.");
    return;
  }

  const data   = window.pcData;
  const dims   = window.pcLabels;
  const yMin   = window.pcYMin ?? 0;
  const yMax   = window.pcYMax ?? 1;

  const svg = d3.select("#pc-svg");
  const { width, height } = svg.node().getBoundingClientRect();
  const margin = { top: 20, right: 20, bottom: 40, left: 40 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scalePoint().domain(dims).range([0, innerW]).padding(0.5);
  const y = d3.scaleLinear().domain([yMin, yMax]).nice().range([innerH, 0]);

  // Ejes
  g.selectAll(".axisY")
    .data(dims)
    .join("g")
    .attr("class", "axisY")
    .attr("transform", d => `translate(${x(d)},0)`)
    .each(function () { d3.select(this).call(d3.axisLeft(y).ticks(6)); })
    .append("text")
    .attr("y", innerH + 30)
    .attr("text-anchor", "middle")
    .attr("fill", "currentColor")
    .text(d => d);

  const line = d3.line()
    .x((d, i) => x(dims[i]))
    .y(v => y(v))
    .defined(v => v != null && !isNaN(v));

  const color = d3.scaleSequential(d3.interpolateTurbo)
                  .domain([0, Math.max(1, data.length - 1)]);
  let pinned = new Set();

  const paths = g.append("g").attr("fill", "none")
    .selectAll("path.solution")
    .data(data, d => d.id)
    .join("path")
    .attr("class", "solution")
    .attr("d", d => line(d.values))
    .attr("stroke", (d, i) => color(i))
    .attr("stroke-opacity", 0.15)
    .attr("stroke-width", 1.5)
    .style("cursor", "pointer")
    .on("mouseover", function (_, d) {
      if (pinned.size === 0) d3.selectAll("path.solution").attr("stroke-opacity", 0.05);
      else d3.selectAll("path.solution").filter(p => !pinned.has(p.id)).attr("stroke-opacity", 0.05);
      d3.select(this).attr("stroke-opacity", 0.95).attr("stroke-width", 2.5);
      tooltip.style("display", "block")
             .html(`<strong>Solution:</strong> ${d.label}<br><em>${dims.map((k,i)=>`${k}: ${(+d.values[i]).toFixed(4)}`).join("<br>")}</em>`);
    })
    .on("mousemove", function (event) {
      tooltip.style("left", (event.pageX + 12) + "px")
             .style("top", (event.pageY + 12) + "px");
    })
    .on("mouseout", function () {
      if (pinned.size === 0)
        d3.selectAll("path.solution").attr("stroke-opacity", 0.15).attr("stroke-width", 1.5);
      else
        d3.selectAll("path.solution")
          .attr("stroke-opacity", p => pinned.has(p.id) ? 0.9 : 0.05)
          .attr("stroke-width",  p => pinned.has(p.id) ? 2.5 : 1.5);
      tooltip.style("display", "none");
    })
    .on("click", function (_, d) {
      pinned.has(d.id) ? pinned.delete(d.id) : pinned.add(d.id);
      d3.selectAll("path.solution")
        .attr("stroke-opacity", p => pinned.size === 0 ? 0.15 : (pinned.has(p.id) ? 0.9 : 0.05))
        .attr("stroke-width",  p => pinned.size === 0 ? 1.5 : (pinned.has(p.id) ? 2.5 : 1.5));
    });

  const tooltip = d3.select("body").append("div")
    .attr("id", "pc-tooltip")
    .style("position", "absolute")
    .style("z-index", 10)
    .style("background", "#fff")
    .style("border", "1px solid #ddd")
    .style("border-radius", "6px")
    .style("padding", "8px 10px")
    .style("font-size", "12px")
    .style("box-shadow", "0 2px 8px rgba(0,0,0,.08)")
    .style("display", "none");
})();
