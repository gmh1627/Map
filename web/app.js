(() => {
  const map = L.map("map", { zoomControl: true, preferCanvas: true, attributionControl: true }).setView([35.5, 105.5], 4);
  const bounds = L.latLngBounds([[17.5, 73.5], [53.6, 135.2]]);
  map.setMaxBounds(bounds.pad(0.08));
  const layers = {};
  let routeData = null;
  let railCitiesData = null;
  let railCityLabelsData = null;
  let networkPromise = null;
  const selectedRouteIds = new Set();
  const speedColors = { "300+": "#9b2c52", "250-299": "#d06b3c", "200-249": "#d59c32", "160-199": "#6a9b55", "120-159": "#3b8b87", "0-119": "#6a7895", unknown: "#aeb9b6" };
  const speedLabels = { "300+": "≥ 300 km/h", "250-299": "250–299 km/h", "200-249": "200–249 km/h", "160-199": "160–199 km/h", "120-159": "120–159 km/h", "0-119": "≤ 119 km/h", unknown: "未标注速度" };
  const $ = (id) => document.getElementById(id);
  // Draw administrative boundaries from dedicated line layers. Polygon rings are not drawn,
  // so a city polygon cannot add a second, slightly displaced outline.
  const styleProvinceFill = { color: "transparent", weight: 0, fillColor: "#f8faf8", fillOpacity: 0 };
  const styleProvinceBoundary = { color: "#71807a", weight: 1.2, fill: false, interactive: false };
  const styleCityBoundary = { color: "#c1cbc7", weight: 0.55, fill: false, interactive: false };
  const styleVisitedCity = { color: "#477b91", weight: 1.1, fillColor: "#c8dfea", fillOpacity: .45 };
  const styleOtherVisitedCity = { color: "#aabbb4", weight: .75, fillColor: "#e1e9e5", fillOpacity: .42 };
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

  async function load(name) { const response = await fetch(`data/${name}.geojson?v=20261005-5`, { cache: "default" }); if (!response.ok) throw new Error(`${name}: ${response.status}`); return response.json(); }
  function geojson(data, options) { return L.geoJSON(data, options); }
  function networkEnabled() { return $("network").checked || $("speedNetwork").checked; }
  function networkStyle(feature) {
    return $("speedNetwork").checked
      ? { color: speedColors[feature.properties.speed_class] || speedColors.unknown, weight: 1.05, opacity: .72 }
      : { color: "#aab5b1", weight: .75, opacity: .68 };
  }
  function addCityLabels(data, className = "city-label", filter = undefined) {
    return geojson(data, { filter, pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: 2.8, color: "#477b91", fillColor: "#477b91", fillOpacity: .9, weight: 0.6 }), onEachFeature: (feature, layer) => layer.bindTooltip(feature.properties.display || "", { permanent: true, direction: "right", className, offset: [4, 0] }) });
  }
  function addStations(data, service, labels = true, visible = true) {
    return geojson(data, {
      filter: (feature) => !service || (feature.properties.services || "").split(",").includes(service),
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: service ? 3.2 : 2.4, color: service === "highspeed" ? "#258b8a" : service === "conventional" ? "#263b42" : "#667d74", fillColor: "#fff", fillOpacity: visible ? 1 : 0, opacity: visible ? 1 : 0, weight: 1.0 }),
      onEachFeature: labels ? (feature, layer) => layer.bindTooltip(feature.properties.name || "", { permanent: true, direction: "right", className: "station-label", offset: [5, 0] }) : undefined,
    });
  }
  function addSpeedLegend() {
    const legend = $("legend");
    legend.innerHTML = '<div class="legend-title">到过路线</div><div class="legend-row"><i class="swatch route-swatch route-swatch--highspeed" aria-hidden="true"></i><span>高铁 / 动车</span></div><div class="legend-row"><i class="swatch route-swatch route-swatch--conventional" aria-hidden="true"></i><span>普速铁路</span></div><div class="legend-title speed-legend-title">设计速度 / 最高速度</div>' + Object.keys(speedLabels).map((key) => `<div class="legend-row"><i class="swatch" style="background:${speedColors[key]}"></i><span>${speedLabels[key]}</span></div>`).join("");
  }
  function refreshRailCities() {
    if (!routeData || !layers.railCities) return;
    const routeCities = new Set((routeData.features || [])
      .filter((feature) => selectedRouteIds.has(Number(feature.properties.seq)))
      .flatMap((feature) => [feature.properties.origin_city, feature.properties.destination_city])
      .filter(Boolean));
    layers.railCities.eachLayer((layer) => {
      layer.setStyle(routeCities.has(layer.feature.properties.display) ? styleVisitedCity : hiddenStyle);
    });
    if (layers.railCityLabels) map.removeLayer(layers.railCityLabels);
    layers.railCityLabels = addCityLabels(railCityLabelsData, "city-label", (feature) => routeCities.has(feature.properties.display));
  }
  function refreshRoutes() {
    if (!routeData || !layers.routeOuter || !layers.routeInner) return;
    const showAllRoutes = $("visited").checked;
    const showHighspeedRoutes = showAllRoutes || $("visitedHighspeed").checked;
    const showConventionalRoutes = showAllRoutes || $("visitedConventional").checked;
    const visibleRoute = (feature) => {
      if (!selectedRouteIds.has(Number(feature.properties.seq))) return false;
      return (feature.properties.service === "highspeed" && showHighspeedRoutes)
        || (feature.properties.service === "conventional" && showConventionalRoutes);
    };
    layers.routeOuter.eachLayer((layer) => {
      layer.setStyle(visibleRoute(layer.feature) ? routeStyle(layer.feature.properties.service, "outer") : hiddenStyle);
    });
    layers.routeInner.eachLayer((layer) => {
      layer.setStyle(visibleRoute(layer.feature) ? routeStyle(layer.feature.properties.service, "inner") : hiddenStyle);
    });
    if (showHighspeedRoutes || showConventionalRoutes) {
      layers.routeOuter.addTo(map);
      layers.routeInner.addTo(map);
    } else {
      map.removeLayer(layers.routeOuter);
      map.removeLayer(layers.routeInner);
    }
  }
  // The complete visited route layer is loaded with the base map. The national network is optional.
  async function ensureNetworkLayers() {
    if (networkPromise) return networkPromise;
    networkPromise = Promise.all([load("railway_network_overview"), load("network_stations")])
      .then(([network, networkStations]) => {
        layers.network = geojson(network, { style: networkStyle });
        layers.networkStations = addStations(networkStations, null, false);
        layers.networkStationLabels = addStations(networkStations, null, true, false);
      })
      .catch((error) => {
        networkPromise = null;
        throw error;
      });
    return networkPromise;
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
    if (!layers.provinceFill) return;
    layers.provinceFill.addTo(map);
    if ($("cityBounds").checked) layers.cityBounds.addTo(map); else map.removeLayer(layers.cityBounds);
    layers.provinceBounds.addTo(map);
    layers.provinceBounds.bringToFront();
    refreshRailCities();
    refreshRoutes();
    refreshNetwork();
    updateZoomDependentLayers();
  }
  function updateZoomDependentLayers() {
    const zoom = map.getZoom();
    [layers.railCities, layers.railCityLabels, layers.otherCities, layers.otherCityLabels, layers.networkStations, layers.networkStationLabels, layers.highspeedStations, layers.conventionalStations].forEach((layer) => { if (layer) map.removeLayer(layer); });
    if ($("visitedCities").checked && zoom >= 5 && layers.railCities) {
      layers.railCities.addTo(map);
      layers.railCityLabels.addTo(map);
    }
    if ($("otherVisitedCities").checked && zoom >= 5) {
      layers.otherCities.addTo(map);
      layers.otherCityLabels.addTo(map);
    }
    if (networkEnabled() && zoom >= 9 && layers.networkStations) layers.networkStations.addTo(map);
    if (networkEnabled() && zoom >= 12 && layers.networkStationLabels) layers.networkStationLabels.addTo(map);
    const showHighspeedStations = $("visitedHighspeed").checked || ($("visited").checked && !$("visitedConventional").checked);
    const showConventionalStations = $("visitedConventional").checked || ($("visited").checked && !$("visitedHighspeed").checked);
    if (zoom >= 7 && showHighspeedStations && layers.highspeedStations) layers.highspeedStations.addTo(map);
    if (zoom >= 7 && showConventionalStations && layers.conventionalStations) layers.conventionalStations.addTo(map);
  }
  function routePopup(feature, layer) {
    const p = feature.properties;
    layer.bindTooltip(`${p.train || ""} · ${p.origin || ""}—${p.destination || ""} · ${p.table_km || 0} km`, { sticky: true, className: "route-tooltip" });
  }
  function renderRouteList() {
    const query = $("routeSearch").value.trim().toLowerCase();
    const rows = routeData.features.filter((feature) => {
      const p = feature.properties;
      return `${p.train} ${p.origin} ${p.destination}`.toLowerCase().includes(query);
    });
    $("routeList").innerHTML = rows.map((feature) => {
      const p = feature.properties;
      const id = Number(p.seq);
      const details = [p.date || "日期未录入", p.time || "时间未录入", `${p.table_km || 0} km`].filter(Boolean).join(" · ");
      return `<label class="route-option"><input type="checkbox" data-route-id="${id}"${selectedRouteIds.has(id) ? " checked" : ""}><span class="route-option-main"><strong>${p.train} · ${p.origin}—${p.destination}</strong><small>${details}</small></span></label>`;
    }).join("") || '<div class="note">没有匹配的路线</div>';
  }
  Promise.all([
    load("provinces"),
    load("province_boundaries"),
    load("city_boundaries"),
    load("rail_visited_cities"),
    load("rail_city_labels"),
    load("other_visited_cities"),
    load("other_city_labels"),
    load("visited_routes"),
    load("visited_stations"),
  ]).then(([provinces, provinceBoundaries, cityBoundaries, railCities, railCityLabels, otherCities, otherCityLabels, routes, stations]) => {
    layers.provinceFill = geojson(provinces, { style: styleProvinceFill });
    layers.provinceBounds = geojson(provinceBoundaries, { style: styleProvinceBoundary });
    layers.cityBounds = geojson(cityBoundaries, { style: styleCityBoundary });
    railCitiesData = railCities;
    railCityLabelsData = railCityLabels;
    layers.railCities = geojson(railCitiesData, { style: styleVisitedCity });
    layers.railCityLabels = addCityLabels(railCityLabelsData);
    layers.otherCities = geojson(otherCities, { style: styleOtherVisitedCity });
    layers.otherCityLabels = addCityLabels(otherCityLabels, "other-city-label");
    routeData = routes;
    routeData.features.forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq)));
    layers.routeOuter = geojson(routeData, { style: (feature) => routeStyle(feature.properties.service, "outer") });
    layers.routeInner = geojson(routeData, { style: (feature) => routeStyle(feature.properties.service, "inner"), onEachFeature: routePopup });
    layers.highspeedStations = addStations(stations, "highspeed");
    layers.conventionalStations = addStations(stations, "conventional");
    layers.provinceFill.addTo(map);
    addSpeedLegend();
    refresh();
    map.fitBounds(bounds, { padding: [12, 12] });
    renderRouteList();
  }).catch((error) => { console.error(error); });
  ["visited", "network", "visitedHighspeed", "visitedConventional", "speedNetwork", "cityBounds", "visitedCities", "otherVisitedCities"].forEach((id) => $(id).addEventListener("change", refresh));
  $("reset").addEventListener("click", () => map.fitBounds(bounds, { padding: [12, 12] }));
  $("routeSearch").addEventListener("input", renderRouteList);
  $("routeList").addEventListener("change", (event) => { const id = Number(event.target.dataset.routeId); if (!Number.isFinite(id)) return; if (event.target.checked) selectedRouteIds.add(id); else selectedRouteIds.delete(id); renderRouteList(); refresh(); });
  $("selectAllRoutes").addEventListener("click", () => { routeData?.features.forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq))); renderRouteList(); refresh(); });
  $("clearRoutes").addEventListener("click", () => { selectedRouteIds.clear(); renderRouteList(); refresh(); });
  map.on("zoomend", updateZoomDependentLayers);
})();
