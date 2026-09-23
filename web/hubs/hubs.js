(() => {
  const HUBS = {
    beijing: { title: "北京及周边", description: "北京枢纽与京北方向的铁路行迹", bounds: [[39.28, 115.20], [41.22, 117.75]], stations: ["北京", "北京丰台", "北京北", "北京南", "北京西", "清河", "大兴机场", "古北口", "八达岭长城"] },
    hefei: { title: "合肥及周边", description: "合肥枢纽与皖江、皖南方向的铁路行迹", bounds: [[30.78, 116.45], [32.70, 118.22]], stations: ["合肥", "合肥南", "合肥北城", "合肥西", "全椒", "滁州北", "芜湖", "宣城", "泾县"] },
    guangzhou: { title: "广州及周边", description: "广州枢纽与粤西、广佛方向的铁路行迹", bounds: [[22.05, 112.70], [24.10, 114.32]], stations: ["广州", "广州东", "广州南", "广州白云", "佛山西", "广州北", "韶关", "湛江北"] },
  };
  const map = L.map("map", { preferCanvas: true, zoomControl: true, attributionControl: true });
  map.createPane("areas").style.zIndex = 210;
  map.createPane("boundaries").style.zIndex = 320;
  map.createPane("routes").style.zIndex = 430;
  map.createPane("stations").style.zIndex = 470;
  const $ = (id) => document.getElementById(id);
  const layers = {};
  let currentKey = "beijing";
  let datasets = null;
  const load = async (name) => {
    const response = await fetch(`../data/${name}.geojson?v=20260923-1`, { cache: "no-store" });
    if (!response.ok) throw new Error(`${name}: ${response.status}`);
    return response.json();
  };
  const inBounds = (coordinates, bounds) => {
    const [southWest, northEast] = bounds;
    const [lon, lat] = coordinates;
    return lon >= southWest[1] && lon <= northEast[1] && lat >= southWest[0] && lat <= northEast[0];
  };
  const routeStyle = (service, inner = false) => service === "highspeed"
    ? { pane: "routes", color: inner ? "#2e7d83" : "#fffdf7", weight: inner ? 2.7 : 5.0, opacity: .97, lineCap: "round", lineJoin: "round" }
    : { pane: "routes", color: inner ? "#fffdf7" : "#283237", weight: inner ? 1.55 : 4.4, opacity: .97, lineCap: "round", lineJoin: "round" };
  const routeTooltip = (feature, layer) => {
    const p = feature.properties;
    layer.bindTooltip(`${p.train || ""} · ${p.origin || ""}—${p.destination || ""} · ${p.table_km || 0} km`, { sticky: true, className: "hub-route-tooltip" });
  };
  function buildTabs() {
    $("hubTabs").innerHTML = Object.entries(HUBS).map(([key, hub]) => `<button class="hub-tab" type="button" role="tab" data-hub="${key}" aria-selected="${key === currentKey}"><span>${hub.title}</span><small>局部图</small></button>`).join("");
    $("hubTabs").addEventListener("click", (event) => { const button = event.target.closest("[data-hub]"); if (button) drawHub(button.dataset.hub); });
  }
  function clearLayers() { Object.values(layers).forEach((layer) => { if (layer && map.hasLayer(layer)) map.removeLayer(layer); }); Object.keys(layers).forEach((key) => { delete layers[key]; }); }
  function relevantRoutes(hub) {
    const stationCoords = new Map(datasets.stations.features.map((feature) => [feature.properties.name, feature.geometry.coordinates]));
    return datasets.routes.features.filter((feature) => {
      const p = feature.properties;
      return inBounds(stationCoords.get(p.origin) || [999, 999], hub.bounds) || inBounds(stationCoords.get(p.destination) || [999, 999], hub.bounds);
    });
  }
  function drawHub(key) {
    currentKey = key;
    const hub = HUBS[key];
    clearLayers();
    map.fitBounds(hub.bounds, { padding: [22, 22] });
    document.querySelectorAll(".hub-tab").forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.hub === key)));
    $("hubTitle").textContent = hub.title;
    $("hubDescription").textContent = hub.description;
    const routes = relevantRoutes(hub);
    const routeIds = new Set(routes.map((feature) => Number(feature.properties.seq)));
    layers.provinces = L.geoJSON(datasets.provinces, { style: { pane: "areas", color: "#f8faf8", weight: .2, fillColor: "#f8faf8", fillOpacity: 1 } }).addTo(map);
    layers.boundaries = L.geoJSON(datasets.cities, { style: { pane: "boundaries", color: "#bac7c1", weight: .65, fill: false } });
    layers.routesOuter = L.geoJSON(datasets.routes, { filter: (feature) => routeIds.has(Number(feature.properties.seq)), style: (feature) => routeStyle(feature.properties.service, false) });
    layers.routesInner = L.geoJSON(datasets.routes, { filter: (feature) => routeIds.has(Number(feature.properties.seq)), style: (feature) => routeStyle(feature.properties.service, true), onEachFeature: routeTooltip });
    const stationNames = new Set(hub.stations);
    layers.stations = L.geoJSON(datasets.stations, { filter: (feature) => stationNames.has(feature.properties.name), pointToLayer: (_, latlng) => L.circleMarker(latlng, { pane: "stations", radius: 3.4, color: "#2e7d83", fillColor: "#fff", fillOpacity: 1, weight: 1.2 }), onEachFeature: (feature, layer) => layer.bindTooltip(feature.properties.name, { permanent: true, direction: "right", offset: [5, 0], className: "hub-station-label" }) });
    layers.cityLabels = L.geoJSON(datasets.cityLabels, { filter: (feature) => inBounds(feature.geometry.coordinates, hub.bounds), pointToLayer: (_, latlng) => L.circleMarker(latlng, { radius: 0, opacity: 0, fillOpacity: 0 }), onEachFeature: (feature, layer) => layer.bindTooltip(feature.properties.display || "", { permanent: true, direction: "right", offset: [4, 0], className: "hub-city-label" }) });
    applyVisibility();
    $("routeCount").textContent = routes.length;
    $("stationCount").textContent = hub.stations.filter((name) => datasets.stationNames.has(name)).length;
    $("routeList").innerHTML = routes.slice().sort((a, b) => Number(a.properties.seq) - Number(b.properties.seq)).map((feature) => { const p = feature.properties; return `<div class="hub-route hub-route--${p.service}"><strong>${p.train || ""} · ${p.origin || ""}—${p.destination || ""}</strong><small>${p.date || "日期未录入"} · ${p.table_km || 0} km${p.time ? ` · ${p.time}` : ""}</small></div>`; }).join("") || '<div class="hub-route">当前范围没有相关行程</div>';
    $("status").textContent = `${hub.title} · ${routes.length} 条相关行程`;
  }
  function applyVisibility() {
    if (!datasets) return;
    const toggle = (id, layer) => { if (!layer) return; if ($(id).checked) layer.addTo(map); else map.removeLayer(layer); };
    toggle("showRoutes", layers.routesOuter); toggle("showRoutes", layers.routesInner); toggle("showCities", layers.boundaries); toggle("showStations", layers.stations); toggle("showLabels", layers.cityLabels);
  }
  Promise.all([load("provinces"), load("city_boundaries"), load("visited_routes"), load("visited_stations"), load("rail_city_labels")]).then(([provinces, cities, routes, stations, cityLabels]) => {
    datasets = { provinces, cities, routes, stations, cityLabels, stationNames: new Set(stations.features.map((feature) => feature.properties.name)) };
    buildTabs();
    drawHub(currentKey);
    ["showRoutes", "showCities", "showStations", "showLabels"].forEach((id) => $(id).addEventListener("change", applyVisibility));
    $("reset").addEventListener("click", () => map.fitBounds(HUBS[currentKey].bounds, { padding: [22, 22] }));
  }).catch((error) => { console.error(error); $("status").textContent = `枢纽数据加载失败：${error.message}`; });
})();
