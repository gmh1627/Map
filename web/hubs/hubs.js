(() => {
  const HUBS = {
    beijing: { title: "北京及周边", bounds: [[39.28, 115.20], [41.22, 117.75]], cities: ["北京", "天津", "张家口", "廊坊", "保定", "承德"] },
    hefei: { title: "合肥及周边", bounds: [[30.78, 116.45], [32.70, 118.22]], cities: ["合肥", "芜湖", "宣城", "马鞍山", "滁州", "六安", "淮南", "巢湖"] },
    guangzhou: { title: "广州及周边", bounds: [[22.05, 112.70], [24.10, 114.32]], cities: ["广州", "佛山", "东莞", "深圳", "中山", "惠州", "韶关", "香港"] },
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
    $("hubTabs").innerHTML = Object.entries(HUBS).map(([key, hub]) => `<button class="hub-tab" type="button" role="tab" data-hub="${key}" aria-selected="${key === currentKey}">${hub.title}</button>`).join("");
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
    const routes = relevantRoutes(hub);
    const routeIds = new Set(routes.map((feature) => Number(feature.properties.seq)));
    layers.provinces = L.geoJSON(datasets.provinces, { style: { pane: "areas", color: "#f8faf8", weight: .2, fillColor: "#f8faf8", fillOpacity: 1 } }).addTo(map);
    layers.boundaries = datasets.cities ? L.geoJSON(datasets.cities, { style: { pane: "boundaries", color: "#c1cbc7", weight: .58, opacity: .8, fill: false } }) : null;
    layers.provinceBoundaries = datasets.provinceBoundaries ? L.geoJSON(datasets.provinceBoundaries, { style: { pane: "boundaries", color: "#71807a", weight: 1.25, opacity: .95, fill: false } }) : null;
    layers.cityHighlights = L.geoJSON(datasets.visitedCities, { filter: (feature) => hub.cities.includes(feature.properties.display), style: { pane: "areas", color: "#7d9c98", weight: .8, fillColor: "#c8dfea", fillOpacity: .62 } });
    layers.routesOuter = L.geoJSON(datasets.routes, { filter: (feature) => routeIds.has(Number(feature.properties.seq)), style: (feature) => routeStyle(feature.properties.service, false) });
    layers.routesInner = L.geoJSON(datasets.routes, { filter: (feature) => routeIds.has(Number(feature.properties.seq)), style: (feature) => routeStyle(feature.properties.service, true), onEachFeature: routeTooltip });
    const stationNames = new Set(datasets.stations.features.filter((feature) => inBounds(feature.geometry.coordinates, hub.bounds)).map((feature) => feature.properties.name));
    layers.stations = L.geoJSON(datasets.stations, { filter: (feature) => stationNames.has(feature.properties.name), pointToLayer: (_, latlng) => L.circleMarker(latlng, { pane: "stations", radius: 3.4, color: "#2e7d83", fillColor: "#fff", fillOpacity: 1, weight: 1.2 }), onEachFeature: (feature, layer) => layer.bindTooltip(feature.properties.name, { permanent: true, direction: "right", offset: [5, 0], className: "hub-station-label" }) });
    layers.cityLabels = L.geoJSON(datasets.cityLabels, { filter: (feature) => hub.cities.includes(feature.properties.display), pointToLayer: (_, latlng) => L.circleMarker(latlng, { radius: 0, opacity: 0, fillOpacity: 0 }), onEachFeature: (feature, layer) => layer.bindTooltip(feature.properties.display || "", { permanent: true, direction: "right", offset: [4, 0], className: "hub-city-label" }) });
    applyVisibility();
    $("routeCount").textContent = routes.length;
    $("stationCount").textContent = stationNames.size;
    $("routeList").innerHTML = routes.slice().sort((a, b) => Number(a.properties.seq) - Number(b.properties.seq)).map((feature) => { const p = feature.properties; return `<div class="hub-route hub-route--${p.service}"><strong>${p.train || ""} · ${p.origin || ""}—${p.destination || ""}</strong><small>${p.date || "日期未录入"} · ${p.table_km || 0} km${p.time ? ` · ${p.time}` : ""}</small></div>`; }).join("") || '<div class="hub-route">当前范围没有相关行程</div>';
    $("status").textContent = "选择枢纽查看局部铁路行程";
  }
  function applyVisibility() {
    if (!datasets) return;
    const toggle = (id, layer) => { if (!layer) return; if ($(id).checked) layer.addTo(map); else map.removeLayer(layer); };
    toggle("showRoutes", layers.routesOuter); toggle("showRoutes", layers.routesInner); toggle("showCities", layers.boundaries); toggle("showCities", layers.provinceBoundaries); toggle("showCities", layers.cityHighlights); toggle("showStations", layers.stations); toggle("showLabels", layers.cityLabels);
  }
  Promise.all([load("provinces"), load("visited_routes"), load("visited_stations"), load("rail_city_labels"), load("rail_visited_cities")]).then(([provinces, routes, stations, cityLabels, visitedCities]) => {
    datasets = { provinces, cities: null, provinceBoundaries: null, routes, stations, cityLabels, visitedCities, stationNames: new Set(stations.features.map((feature) => feature.properties.name)) };
    buildTabs();
    drawHub(currentKey);
    Promise.all([load("city_boundaries"), load("province_boundaries")]).then(([cities, provinceBoundaries]) => { datasets.cities = cities; datasets.provinceBoundaries = provinceBoundaries; drawHub(currentKey); });
    ["showRoutes", "showCities", "showStations", "showLabels"].forEach((id) => $(id).addEventListener("change", applyVisibility));
    $("reset").addEventListener("click", () => map.fitBounds(HUBS[currentKey].bounds, { padding: [22, 22] }));
  }).catch((error) => { console.error(error); $("status").textContent = `枢纽数据加载失败：${error.message}`; });
})();
