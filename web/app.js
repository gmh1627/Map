(() => {
  const map = L.map("map", { zoomControl: true, preferCanvas: true, attributionControl: true }).setView([35.5, 105.5], 4);
  const bounds = L.latLngBounds([[17.5, 73.5], [53.6, 135.2]]);
  map.setMaxBounds(bounds.pad(0.08));
  const layers = {};
  let routeData = null;
  let railCitiesData = null;
  let railCityLabelsData = null;
  const selectedRouteIds = new Set();
  const speedColors = { "300+": "#9b2c52", "250-299": "#d06b3c", "200-249": "#d59c32", "160-199": "#6a9b55", "120-159": "#3b8b87", "0-119": "#6a7895", unknown: "#aeb9b6" };
  const speedLabels = { "300+": "≥ 300 km/h", "250-299": "250–299 km/h", "200-249": "200–249 km/h", "160-199": "160–199 km/h", "120-159": "120–159 km/h", "0-119": "≤ 119 km/h", unknown: "未标注速度" };
  const $ = (id) => document.getElementById(id);
  const styleProvince = { color: "#71807a", weight: 1.2, fillColor: "#f8faf8", fillOpacity: 0 };
  const styleCities = { color: "#c1cbc7", weight: 0.55, fill: false };
  const styleVisitedCity = { color: "#477b91", weight: 1.1, fillColor: "#c8dfea", fillOpacity: .45 };
  const styleOtherVisitedCity = { color: "#aabbb4", weight: .75, fillColor: "#e1e9e5", fillOpacity: .42 };
  const styleRoute = (service) => service === "highspeed" ? { color: "#258b8a", weight: 2.6, opacity: .9 } : { color: "#263b42", weight: 2.1, opacity: .88 };

  async function load(name) { const response = await fetch(`data/${name}.geojson?v=20260914-2`); if (!response.ok) throw new Error(`${name}: ${response.status}`); return response.json(); }
  function geojson(data, options) { return L.geoJSON(data, options); }
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
    legend.innerHTML = '<div class="legend-title">到过路线</div><div class="legend-row"><i class="swatch route-swatch" style="color:#258b8a"></i><span>高铁 / 动车</span></div><div class="legend-row"><i class="swatch route-swatch" style="color:#263b42"></i><span>普速铁路</span></div><div class="legend-title speed-legend-title">设计速度 / 最高速度</div>' + Object.keys(speedLabels).map((key) => `<div class="legend-row"><i class="swatch" style="background:${speedColors[key]}"></i><span>${speedLabels[key]}</span></div>`).join("");
  }
  function refresh() {
    Object.values(layers).forEach((layer) => map.removeLayer(layer));
    layers.provinces.addTo(map);
    if ($("cityBounds").checked) layers.cities.addTo(map);
    if (routeData) {
      const routeCities = new Set((routeData?.features || []).filter((feature) => selectedRouteIds.has(Number(feature.properties.seq))).flatMap((feature) => [feature.properties.origin_city, feature.properties.destination_city]).filter(Boolean));
      layers.railCities = geojson(railCitiesData, { filter: (feature) => routeCities.has(feature.properties.display), style: styleVisitedCity });
      layers.railCityLabels = addCityLabels(railCityLabelsData, "city-label", (feature) => routeCities.has(feature.properties.display));
    }
    // Draw the province outline after city boundaries so shared borders stay continuous.
    layers.provinces.bringToFront();
    if ($("network").checked || $("speedNetwork").checked) {
      layers.network.setStyle((feature) => $("speedNetwork").checked
        ? { color: speedColors[feature.properties.speed_class] || speedColors.unknown, weight: 1.05, opacity: .72 }
        : { color: "#aab5b1", weight: .75, opacity: .68 });
      layers.network.addTo(map);
    }
    if (routeData) {
      layers.routeCasing = geojson(routeData, { filter: (feature) => selectedRouteIds.has(Number(feature.properties.seq)), style: () => ({ color: "#fffdf7", weight: 4.2, opacity: .96 }), onEachFeature: routePopup });
      layers.visited = geojson(routeData, { filter: (feature) => selectedRouteIds.has(Number(feature.properties.seq)), style: (feature) => styleRoute(feature.properties.service), onEachFeature: routePopup });
      layers.highspeed = geojson(routeData, { filter: (feature) => selectedRouteIds.has(Number(feature.properties.seq)) && feature.properties.service === "highspeed", style: () => styleRoute("highspeed"), onEachFeature: routePopup });
      layers.conventional = geojson(routeData, { filter: (feature) => selectedRouteIds.has(Number(feature.properties.seq)) && feature.properties.service === "conventional", style: () => styleRoute("conventional"), onEachFeature: routePopup });
    }
    if (routeData && ($("visited").checked || $("visitedHighspeed").checked || $("visitedConventional").checked)) layers.routeCasing.addTo(map);
    if (routeData && $("visited").checked) layers.visited.addTo(map);
    if (routeData && $("visitedHighspeed").checked) layers.highspeed.addTo(map);
    if (routeData && $("visitedConventional").checked) layers.conventional.addTo(map);
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
    if (($("network").checked || $("speedNetwork").checked) && zoom >= 9) layers.networkStations.addTo(map);
    if (($("network").checked || $("speedNetwork").checked) && zoom >= 12) layers.networkStationLabels.addTo(map);
    const showHighspeedStations = $("visitedHighspeed").checked || ($("visited").checked && !$("visitedConventional").checked);
    const showConventionalStations = $("visitedConventional").checked || ($("visited").checked && !$("visitedHighspeed").checked);
    if (zoom >= 7 && showHighspeedStations) layers.highspeedStations.addTo(map);
    if (zoom >= 7 && showConventionalStations) layers.conventionalStations.addTo(map);
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
      return `<label class="route-option"><input type="checkbox" data-route-id="${id}"${selectedRouteIds.has(id) ? " checked" : ""}><span class="route-option-main"><strong>${p.train} · ${p.origin}—${p.destination}</strong><small>${p.date || "日期未录入"} · 时间未录入 · ${p.table_km || 0} km</small></span></label>`;
    }).join("") || '<div class="note">没有匹配的路线</div>';
  }
  Promise.all([load("provinces"), load("cities"), load("visited_cities"), load("visited_city_labels"), load("rail_visited_cities"), load("rail_city_labels"), load("other_visited_cities"), load("other_city_labels"), load("railway_network"), load("visited_routes"), load("visited_stations"), load("network_stations")]).then(([provinces, cities, visitedCities, labels, railCities, railCityLabels, otherCities, otherCityLabels, network, routes, stations, networkStations]) => {
    layers.provinces = geojson(provinces, { style: styleProvince });
    layers.cities = geojson(cities, { style: styleCities });
    layers.visitedCities = geojson(visitedCities, { style: styleVisitedCity });
    layers.cityLabels = addCityLabels(labels);
    railCitiesData = railCities;
    railCityLabelsData = railCityLabels;
    layers.otherCities = geojson(otherCities, { style: styleOtherVisitedCity });
    layers.otherCityLabels = addCityLabels(otherCityLabels, "other-city-label");
    layers.network = geojson(network, { style: (feature) => ({ color: speedColors[feature.properties.speed_class] || speedColors.unknown, weight: 1.05, opacity: .7 }) });
    routeData = routes;
    routeData.features.forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq)));
    layers.highspeedStations = addStations(stations, "highspeed");
    layers.conventionalStations = addStations(stations, "conventional");
    layers.networkStations = addStations(networkStations, null, false);
    layers.networkStationLabels = addStations(networkStations, null, true, false);
    layers.provinces.addTo(map);
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
  map.on("zoomend", () => { if (layers.network) updateZoomDependentLayers(); });
})();
