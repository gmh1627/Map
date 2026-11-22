(() => {
  const map = L.map("map", { zoomControl: true, preferCanvas: true, attributionControl: true }).setView([35.5, 105.5], 4);
  const bounds = L.latLngBounds([[17.5, 73.5], [53.6, 135.2]]);
  const HUBS = {
    all: { label: "全部范围", bounds },
    beijing: { label: "北京及周边", bounds: [[39.28, 115.20], [41.22, 117.75]] },
    hefei: { label: "合肥及周边", bounds: [[30.78, 116.45], [32.70, 118.22]] },
    guangzhou: { label: "广州及周边", bounds: [[22.05, 112.70], [24.10, 114.32]] },
  };
  map.setMaxBounds(bounds.pad(0.08));
  const layers = {};
  let routeData = null;
  let visitedStationsData = null;
  let railCityLabelsData = null;
  let networkPromise = null;
  let networkStationPromise = null;
  const cityPromises = {};
  let cityLabelKey = null;
  let stationKey = null;
  const DATA_VERSION = "d75830c02eba";
  const selectedYears = new Set();
  let selectedHub = "all";
  const stationCoordinates = new Map();
  const selectedRouteIds = new Set();
  const speedColors = { "300+": "#9b2c52", "250-299": "#d06b3c", "200-249": "#d59c32", "160-199": "#6a9b55", "120-159": "#3b8b87", "0-119": "#6a7895", unknown: "#aeb9b6" };
  const speedLabels = { "300+": "≥ 300 km/h", "250-299": "250–299 km/h", "200-249": "200–249 km/h", "160-199": "160–199 km/h", "120-159": "120–159 km/h", "0-119": "≤ 119 km/h", unknown: "未标注速度" };
  const $ = (id) => document.getElementById(id);
  // Draw administrative boundaries from dedicated line layers. Polygon rings are not drawn,
  // so a city polygon cannot add a second, slightly displaced outline.
  const styleProvinceBoundary = { color: "#727d78", weight: 1.2, fill: false, interactive: false };
  const styleCityBoundary = { color: "#a8b8c4", weight: 0.55, fill: false, interactive: false };
  // Static railway maps use transparent polygon outlines. Administrative lines
  // are drawn separately, with the province boundary above the city boundary.
  const styleVisitedCity = { color: "transparent", weight: 0, fillColor: "#b5d3e8", fillOpacity: .18 };
  const styleOtherVisitedCity = { color: "transparent", weight: 0, fillColor: "#e1e9e5", fillOpacity: .42 };
  const hiddenStyle = { color: "transparent", weight: 0, opacity: 0, fillOpacity: 0 };
  // Keep the web map in the same two-layer language as the static QGIS maps:
  // high-speed routes use a light casing and coloured core; conventional
  // routes use a dark casing and light core.
  const routeStyle = (service, layer) => {
    if (service === "highspeed") {
      return layer === "outer"
        ? { color: "#fffdf7", weight: 4.8, opacity: .98, lineCap: "round", lineJoin: "round" }
        : { color: "#2e7d83", weight: 2.55, opacity: .95, lineCap: "round", lineJoin: "round" };
    }
    return layer === "outer"
      ? { color: "#283237", weight: 4.2, opacity: .96, lineCap: "round", lineJoin: "round" }
      : { color: "#fffdf7", weight: 1.55, opacity: .98, lineCap: "round", lineJoin: "round" };
  };

  async function load(name) { const response = await fetch(`data/${name}.geojson?v=${DATA_VERSION}`, { cache: "default" }); if (!response.ok) throw new Error(`${name}: ${response.status}`); return response.json(); }
  async function loadStartup() {
    if (typeof DecompressionStream === "undefined") {
      const names = ["province_boundaries", "city_boundaries", "rail_city_labels", "other_city_labels", "visited_routes", "visited_stations"];
      return Object.fromEntries(await Promise.all(names.map(async (name) => [name, await load(name)])));
    }
    const response = await fetch(`data/startup.json.gz?v=${DATA_VERSION}`, { cache: "default" });
    if (!response.ok) throw new Error(`startup: ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const text = bytes[0] === 31 && bytes[1] === 139
      ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).text()
      : new TextDecoder().decode(bytes);
    return RailMapData.unpack(JSON.parse(text));
  }
  function routeYear(feature) {
    return String(feature.properties.date || "").match(/\d{4}/)?.[0] || "unknown";
  }
  function yearVisible(feature) {
    return selectedYears.size === 0 || selectedYears.has(routeYear(feature));
  }
  function yearLabel() {
    if (selectedYears.size === 0) return "全部年份";
    const years = [...selectedYears].filter((year) => year !== "unknown").sort((a, b) => b.localeCompare(a));
    return [years.length ? `${years.join("、")} 年` : "", selectedYears.has("unknown") ? "日期不详" : ""].filter(Boolean).join("、");
  }
  function hubVisible(feature) {
    if (selectedHub === "all") return true;
    const [southWest, northEast] = HUBS[selectedHub].bounds;
    return [feature.properties.origin, feature.properties.destination].some((name) => {
      const point = stationCoordinates.get(name);
      return point && point[0] >= southWest[1] && point[0] <= northEast[1]
        && point[1] >= southWest[0] && point[1] <= northEast[0];
    });
  }
  function scopeVisible(feature) {
    return yearVisible(feature) && hubVisible(feature);
  }
  function selectScopedRoutes() {
    selectedRouteIds.clear();
    routeData.features.filter(scopeVisible).forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq)));
    $("routeSearch").value = "";
  }
  function fitHub() {
    map.stop();
    map.fitBounds(HUBS[selectedHub].bounds, { padding: [12, 12], animate: false });
  }
  function renderYearFilters() {
    const years = [...new Set(routeData.features.map(routeYear))].sort((a, b) => b.localeCompare(a));
    $("yearFilters").innerHTML = ["all", ...years].map((year) => {
      const label = year === "all" ? "全部年份" : year === "unknown" ? "日期不详" : `${year} 年`;
      const active = year === "all" ? selectedYears.size === 0 : selectedYears.has(year);
      return `<button class="year-filter" type="button" data-year="${year}" aria-pressed="${active}">${label}</button>`;
    }).join("");
  }
  function renderSummary() {
    const records = routeData.features.filter(routeVisibility).map((feature) => feature.properties);
    const conventional = records.filter((record) => record.service === "conventional");
    const highspeed = records.filter((record) => record.service === "highspeed");
    const distance = (items) => items.reduce((total, record) => total + Number(record.table_km || 0), 0);
    const cities = new Set(records.flatMap((record) => [record.origin_city, record.destination_city]).filter(Boolean));
    const stations = new Set(records.flatMap((record) => [record.origin, record.destination]).filter(Boolean));
    const values = {
      summaryTrips: records.length,
      summaryConventional: conventional.length,
      summaryHighspeed: highspeed.length,
      summaryDistance: distance(records),
      summaryConventionalKm: distance(conventional),
      summaryHighspeedKm: distance(highspeed),
      summaryCities: cities.size,
      summaryStations: stations.size,
    };
    Object.entries(values).forEach(([id, value]) => { $(id).textContent = value.toLocaleString("en-US"); });
    $("summaryLabel").textContent = selectedYears.size === 0 ? "铁路足迹" : `${yearLabel()}铁路足迹`;
    $("status").textContent = [selectedHub === "all" ? "" : HUBS[selectedHub].label, yearLabel(), `${records.length} 段行程`].filter(Boolean).join(" · ");
  }
  function geojson(data, options) { return L.geoJSON(data, options); }
  function networkEnabled() { return $("network").checked || $("speedNetwork").checked; }
  function networkStyle(feature) {
    return $("speedNetwork").checked
      ? { color: speedColors[feature.properties.speed_class] || speedColors.unknown, weight: 1.05, opacity: .72 }
      : { color: "#aab5b1", weight: .75, opacity: .68 };
  }
  function stationStyle(service, visible = true) {
    return {
      radius: service ? 3.2 : 2.4,
      color: service === "highspeed" ? "#258b8a" : service === "conventional" ? "#263b42" : "#667d74",
      fillColor: "#fff",
      fillOpacity: visible ? 1 : 0,
      opacity: visible ? 1 : 0,
      weight: 1.0,
    };
  }
  function addCityLabels(data, className = "city-label", filter = undefined) {
    return geojson(data, { filter, pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: 2.8, color: "#477b91", fillColor: "#477b91", fillOpacity: .9, weight: 0.6 }), onEachFeature: (feature, layer) => layer.bindTooltip(feature.properties.display || "", { permanent: true, direction: "right", className, offset: [4, 0] }) });
  }
  function addStations(data, service, labels = true, visible = true, stationNames = null) {
    return geojson(data, {
      filter: (feature) => (!service || (feature.properties.services || "").split(",").includes(service))
        && (!stationNames || stationNames.has(feature.properties.name)),
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, stationStyle(service, visible)),
      onEachFeature: labels ? (feature, layer) => layer.bindTooltip(feature.properties.name || "", { permanent: true, direction: "right", className: "station-label", offset: [5, 0] }) : undefined,
    });
  }
  function addSpeedLegend() {
    const legend = $("legend");
    legend.innerHTML = '<div class="legend-title">到过路线</div><div class="legend-row"><i class="swatch route-swatch route-swatch--highspeed" aria-hidden="true"></i><span>高铁 / 动车</span></div><div class="legend-row"><i class="swatch route-swatch route-swatch--conventional" aria-hidden="true"></i><span>普速铁路</span></div><div class="legend-title speed-legend-title">设计速度 / 最高速度</div>' + Object.keys(speedLabels).map((key) => `<div class="legend-row"><i class="swatch" style="background:${speedColors[key]}"></i><span>${speedLabels[key]}</span></div>`).join("");
  }
  function refreshRailCities() {
    if (!routeData) return;
    const routeCities = new Set((routeData.features || [])
      .filter((feature) => routeVisibility(feature))
      .flatMap((feature) => [feature.properties.origin_city, feature.properties.destination_city])
      .filter(Boolean));
    layers.railCities?.eachLayer((layer) => {
      layer.setStyle(routeCities.has(layer.feature.properties.display) ? styleVisitedCity : hiddenStyle);
    });
    const key = [...routeCities].sort().join("|");
    if (key === cityLabelKey) return;
    cityLabelKey = key;
    if (layers.railCityLabels) map.removeLayer(layers.railCityLabels);
    layers.railCityLabels = addCityLabels(railCityLabelsData, "city-label", (feature) => routeCities.has(feature.properties.display));
  }
  function selectedServiceVisibility() {
    const highspeed = $("visitedHighspeed").checked;
    const conventional = $("visitedConventional").checked;
    if (highspeed || conventional) return { highspeed, conventional };
    const all = $("visited").checked;
    return { highspeed: all, conventional: all };
  }
  function serviceVisible(feature) {
    return Boolean(selectedServiceVisibility()[feature.properties.service]);
  }
  function routeVisibility(feature) {
    return scopeVisible(feature) && selectedRouteIds.has(Number(feature.properties.seq)) && serviceVisible(feature);
  }
  function refreshStations() {
    if (!routeData || !visitedStationsData) return;
    const visibleNames = { highspeed: new Set(), conventional: new Set() };
    routeData.features.forEach((feature) => {
      if (!routeVisibility(feature)) return;
      const service = feature.properties.service;
      if (!visibleNames[service]) return;
      [feature.properties.origin, feature.properties.destination].filter(Boolean).forEach((name) => visibleNames[service].add(name));
    });
    const key = JSON.stringify(Object.entries(visibleNames).map(([service, names]) => [service, [...names].sort()]));
    if (key === stationKey) return;
    stationKey = key;
    ["highspeedStations", "conventionalStations"].forEach((key) => {
      if (layers[key]) map.removeLayer(layers[key]);
    });
    layers.highspeedStations = addStations(visitedStationsData, "highspeed", true, true, visibleNames.highspeed);
    layers.conventionalStations = addStations(visitedStationsData, "conventional", true, true, visibleNames.conventional);
  }
  function refreshRoutes() {
    if (!routeData || !layers.routeOuter || !layers.routeInner) return;
    for (const [key, part] of [["routeOuter", "outer"], ["routeInner", "inner"]]) {
      layers[key].eachLayer((layer) => {
        const visible = routeVisibility(layer.feature);
        if (layer._railVisible === visible) return;
        if (layer._railVisible !== undefined || !visible) layer.setStyle(visible ? routeStyle(layer.feature.properties.service, part) : hiddenStyle);
        layer._railVisible = visible;
      });
    }
    if (layers.routeOuter.getLayers().some((layer) => routeVisibility(layer.feature))) {
      layers.routeOuter.addTo(map);
      layers.routeInner.addTo(map);
    } else {
      map.removeLayer(layers.routeOuter);
      map.removeLayer(layers.routeInner);
    }
  }
  function ensureCityLayer(kind) {
    if (cityPromises[kind]) return cityPromises[kind];
    const name = kind === "rail" ? "rail_visited_cities" : "other_visited_cities";
    cityPromises[kind] = load(name).then((data) => {
      layers[kind === "rail" ? "railCities" : "otherCities"] = geojson(data, { style: kind === "rail" ? styleVisitedCity : styleOtherVisitedCity });
      refreshRailCities();
      updateZoomDependentLayers();
      raiseForegroundLayers();
    }).catch((error) => { delete cityPromises[kind]; console.error("城市图层加载失败", error); });
    return cityPromises[kind];
  }
  // Exact routes use a shared compressed payload. Optional polygons and
  // national network/station layers are fetched when they become visible.
  async function ensureNetworkLayers() {
    if (networkPromise) return networkPromise;
    networkPromise = load("railway_network_overview")
      .then((network) => {
        layers.network = geojson(network, { style: networkStyle });
      })
      .catch((error) => {
        networkPromise = null;
        throw error;
      });
    return networkPromise;
  }
  function ensureNetworkStations() {
    if (networkStationPromise) return networkStationPromise;
    networkStationPromise = load("network_stations").then((data) => {
      layers.networkStations = addStations(data, null, false);
      layers.networkStationData = data;
      updateZoomDependentLayers();
    }).catch((error) => { networkStationPromise = null; console.error("全国车站加载失败", error); });
    return networkStationPromise;
  }
  function refreshNetwork() {
    if (!networkEnabled()) {
      if (layers.network) map.removeLayer(layers.network);
      if (layers.networkStations) map.removeLayer(layers.networkStations);
      if (layers.networkStationLabels) map.removeLayer(layers.networkStationLabels);
      return;
    }
    ensureNetworkLayers().then(() => {
      if (!networkEnabled()) return;
      layers.network.setStyle(networkStyle);
      layers.network.addTo(map);
      updateZoomDependentLayers();
    }).catch((error) => console.error("全国铁路底图加载失败", error));
  }
  function refresh() {
    if (!layers.provinceBounds) return;
    if ($("cityBounds").checked) layers.cityBounds.addTo(map); else map.removeLayer(layers.cityBounds);
    layers.provinceBounds.addTo(map);
    layers.provinceBounds.bringToFront();
    refreshRailCities();
    refreshRoutes();
    refreshStations();
    refreshNetwork();
    updateZoomDependentLayers();
    raiseForegroundLayers();
    if (routeData) {
      renderRouteList();
      renderSummary();
    }
  }
  function raiseForegroundLayers() {
    if (layers.provinceBounds) layers.provinceBounds.bringToFront();
    if (layers.cityBounds && $("cityBounds").checked) layers.cityBounds.bringToFront();
    if (layers.routeOuter) layers.routeOuter.bringToFront();
    if (layers.routeInner) layers.routeInner.bringToFront();
    if (layers.highspeedStations) layers.highspeedStations.bringToFront();
    if (layers.conventionalStations) layers.conventionalStations.bringToFront();
    if (layers.railCityLabels) layers.railCityLabels.bringToFront();
    if (layers.otherCityLabels) layers.otherCityLabels.bringToFront();
  }
  function addVisibleStations(layer) {
    if (!layer) return;
    layer.addTo(map);
    layer.eachLayer((station) => station.openTooltip());
  }
  function updateZoomDependentLayers() {
    const zoom = map.getZoom();
    [layers.railCities, layers.railCityLabels, layers.otherCities, layers.otherCityLabels, layers.networkStations, layers.networkStationLabels, layers.highspeedStations, layers.conventionalStations].forEach((layer) => { if (layer) map.removeLayer(layer); });
    if ($("visitedCities").checked && zoom >= 5) {
      if (layers.railCities) layers.railCities.addTo(map); else ensureCityLayer("rail");
      layers.railCityLabels?.addTo(map);
    }
    if ($("otherVisitedCities").checked && zoom >= 5) {
      if (layers.otherCities) layers.otherCities.addTo(map); else ensureCityLayer("other");
      layers.otherCityLabels.addTo(map);
    }
    if (networkEnabled() && zoom >= 9) {
      if (layers.networkStations) layers.networkStations.addTo(map); else ensureNetworkStations();
    }
    if (networkEnabled() && zoom >= 12 && layers.networkStationData) {
      if (!layers.networkStationLabels) layers.networkStationLabels = addStations(layers.networkStationData, null, true, false);
      layers.networkStationLabels.addTo(map);
    }
    const showHighspeedStations = $("visitedHighspeed").checked || ($("visited").checked && !$("visitedConventional").checked);
    const showConventionalStations = $("visitedConventional").checked || ($("visited").checked && !$("visitedHighspeed").checked);
    if (zoom >= 7 && showHighspeedStations) addVisibleStations(layers.highspeedStations);
    if (zoom >= 7 && showConventionalStations) addVisibleStations(layers.conventionalStations);
  }
  function routePopup(feature, layer) {
    const p = feature.properties;
    layer.bindTooltip(`${p.train || ""} · ${p.origin || ""}—${p.destination || ""} · ${p.table_km || 0} km`, { sticky: true, className: "route-tooltip" });
  }
  function renderRouteList() {
    const query = $("routeSearch").value.trim().toLowerCase();
    const rows = routeData.features.filter((feature) => {
      const p = feature.properties;
      return scopeVisible(feature) && serviceVisible(feature)
        && `${p.train} ${p.origin} ${p.destination}`.toLowerCase().includes(query);
    });
    $("routeListHeading").textContent = `${rows.length} 段相关行程`;
    $("routeList").innerHTML = rows.map((feature) => {
      const p = feature.properties;
      const id = Number(p.seq);
      const details = [p.date || "日期未录入", p.time || "时间未录入", `${p.table_km || 0} km`].filter(Boolean).join(" · ");
      return `<label class="route-option"><input type="checkbox" data-route-id="${id}"${selectedRouteIds.has(id) ? " checked" : ""}><span class="route-option-main"><strong>${p.train} · ${p.origin}—${p.destination}</strong><small>${details}</small></span></label>`;
    }).join("") || '<div class="note">没有匹配的路线</div>';
  }
  loadStartup().then((data) => {
    const { province_boundaries: provinceBoundaries, city_boundaries: cityBoundaries, rail_city_labels: railCityLabels, other_city_labels: otherCityLabels, visited_routes: routes, visited_stations: stations } = data;
    layers.provinceBounds = geojson(provinceBoundaries, { style: styleProvinceBoundary });
    layers.cityBounds = geojson(cityBoundaries, { style: styleCityBoundary });
    railCityLabelsData = railCityLabels;
    layers.railCityLabels = addCityLabels(railCityLabelsData);
    layers.otherCityLabels = addCityLabels(otherCityLabels, "other-city-label");
    routeData = routes;
    renderYearFilters();
    routeData.features.forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq)));
    layers.routeOuter = geojson(routeData, { style: (feature) => routeStyle(feature.properties.service, "outer") });
    layers.routeInner = geojson(routeData, { style: (feature) => routeStyle(feature.properties.service, "inner"), onEachFeature: routePopup });
    visitedStationsData = stations;
    stations.features.forEach((feature) => stationCoordinates.set(feature.properties.name, feature.geometry.coordinates));
    addSpeedLegend();
    refresh();
    fitHub();
    performance.mark("rail-map-ready");
  }).catch((error) => { console.error(error); $("status").textContent = "地图加载失败，请刷新重试"; });
  ["visited", "network", "visitedHighspeed", "visitedConventional", "speedNetwork", "cityBounds", "visitedCities", "otherVisitedCities"].forEach((id) => $(id).addEventListener("change", refresh));
  $("reset").addEventListener("click", fitHub);
  $("routeSearch").addEventListener("input", renderRouteList);
  $("yearFilters").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-year]");
    if (!button || !routeData) return;
    const year = button.dataset.year;
    if (year === "all") selectedYears.clear();
    else if (selectedYears.has(year)) selectedYears.delete(year);
    else selectedYears.add(year);
    selectScopedRoutes();
    renderYearFilters();
    refresh();
  });
  $("hubFilters").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-hub]");
    if (!button || !routeData || !HUBS[button.dataset.hub]) return;
    selectedHub = button.dataset.hub;
    $("hubFilters").querySelectorAll("button[data-hub]").forEach((tab) => {
      tab.setAttribute("aria-pressed", String(tab.dataset.hub === selectedHub));
    });
    selectScopedRoutes();
    refresh();
    fitHub();
  });
  $("routeList").addEventListener("change", (event) => { const id = Number(event.target.dataset.routeId); if (!Number.isFinite(id)) return; if (event.target.checked) selectedRouteIds.add(id); else selectedRouteIds.delete(id); renderRouteList(); refresh(); });
  $("selectAllRoutes").addEventListener("click", () => { routeData?.features.filter(scopeVisible).forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq))); refresh(); });
  $("clearRoutes").addEventListener("click", () => { selectedRouteIds.clear(); renderRouteList(); refresh(); });
  map.on("zoomend", updateZoomDependentLayers);
})();
