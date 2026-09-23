(() => {
  const map = L.map("map", { zoomControl: true, preferCanvas: true, attributionControl: true }).setView([35.5, 105.5], 4);
  const bounds = L.latLngBounds([[3.0, 73.5], [53.6, 135.2]]);
  map.setMaxBounds(bounds.pad(0.08));
  const layers = {};
  let routeData = null;
  let railCitiesData = null;
  let railCityLabelsData = null;
  let visitedStationsData = null;
  const selectedRouteIds = new Set();
  const speedColors = { "300+": "#9b2c52", "250-299": "#d06b3c", "200-249": "#d59c32", "160-199": "#6a9b55", "120-159": "#3b8b87", "0-119": "#6a7895", unknown: "#aeb9b6" };
  const speedLabels = { "300+": "≥ 300 km/h", "250-299": "250–299 km/h", "200-249": "200–249 km/h", "160-199": "160–199 km/h", "120-159": "120–159 km/h", "0-119": "≤ 119 km/h", unknown: "未标注速度" };
  const $ = (id) => document.getElementById(id);
  $("blogHome").hidden = !window.location.pathname.startsWith("/map/");
  map.createPane("areaFill").style.zIndex = 210;
  map.createPane("adminBoundary").style.zIndex = 320;
  map.createPane("railNetwork").style.zIndex = 400;
  map.createPane("tripRoutes").style.zIndex = 450;
  const styleProvince = { pane: "areaFill", stroke: false, fillColor: "#f8faf8", fillOpacity: 1 };
  const styleCities = { pane: "adminBoundary", color: "#c1cbc7", weight: 0.65, fill: false };
  const styleProvinceBoundary = { pane: "adminBoundary", color: "#71807a", weight: 1.35, fill: false };
  const styleVisitedCity = { pane: "areaFill", stroke: false, fillColor: "#c8dfea", fillOpacity: .58 };
  const styleOtherVisitedCity = { pane: "areaFill", stroke: false, fillColor: "#e1e9e5", fillOpacity: .48 };
  // Keep the web map in the same two-layer language as the static QGIS maps:
  // high-speed routes use a light casing and coloured core; conventional
  // routes use a dark casing and light core.
  const routeStyle = (service, layer) => {
    if (service === "highspeed") {
      return layer === "outer"
        ? { pane: "tripRoutes", color: "#fffdf7", weight: 4.8, opacity: .98, lineCap: "round", lineJoin: "round" }
        : { pane: "tripRoutes", color: "#2e7d83", weight: 2.55, opacity: .95, lineCap: "round", lineJoin: "round" };
    }
    return layer === "outer"
      ? { pane: "tripRoutes", color: "#283237", weight: 4.2, opacity: .96, lineCap: "round", lineJoin: "round" }
      : { pane: "tripRoutes", color: "#fffdf7", weight: 1.55, opacity: .98, lineCap: "round", lineJoin: "round" };
  };

  async function load(name) { const response = await fetch(`data/${name}.geojson?v=20260923-3`, { cache: "no-store" }); if (!response.ok) throw new Error(`${name}: ${response.status}`); return response.json(); }
  function geojson(data, options) { return L.geoJSON(data, options); }
  let networkLoadPromise = null;
  let networkStationsLoadPromise = null;
  async function ensureNetworkLayers() {
    if (layers.network) return;
    if (!networkLoadPromise) {
      const toggles = [$("network"), $("speedNetwork")];
      toggles.forEach((toggle) => { toggle.disabled = true; });
      networkLoadPromise = load("railway_network")
        .then((network) => {
          layers.network = geojson(network, { style: (feature) => ({ pane: "railNetwork", color: speedColors[feature.properties.speed_class] || speedColors.unknown, weight: 1.05, opacity: .7 }) });
        })
        .catch((error) => {
          networkLoadPromise = null;
          throw error;
        })
        .finally(() => { toggles.forEach((toggle) => { toggle.disabled = false; }); });
    }
    await networkLoadPromise;
  }
  async function ensureNetworkStations() {
    if (layers.networkStations) return;
    if (!networkStationsLoadPromise) {
      networkStationsLoadPromise = load("network_stations").then((networkStations) => {
        layers.networkStations = addStations(networkStations, null, false);
        layers.networkStationLabels = addStations(networkStations, null, true, false);
      }).catch((error) => {
        networkStationsLoadPromise = null;
        throw error;
      });
    }
    await networkStationsLoadPromise;
  }
  function addCityLabels(data, className = "city-label", filter = undefined) {
    return geojson(data, { filter, pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: 2.8, color: "#477b91", fillColor: "#477b91", fillOpacity: .9, weight: 0.6 }), onEachFeature: (feature, layer) => layer.bindTooltip(feature.properties.display || "", { permanent: true, direction: "right", className, offset: [4, 0] }) });
  }
  function addStations(data, service, labels = true, visible = true, names = null) {
    return geojson(data, {
      filter: (feature) => (!service || (feature.properties.services || "").split(",").includes(service)) && (!names || names.has(feature.properties.name)),
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: service ? 3.2 : 2.4, color: service === "highspeed" ? "#258b8a" : service === "conventional" ? "#263b42" : "#667d74", fillColor: "#fff", fillOpacity: visible ? 1 : 0, opacity: visible ? 1 : 0, weight: 1.0 }),
      onEachFeature: labels ? (feature, layer) => layer.bindTooltip(feature.properties.name || "", { permanent: true, direction: "right", className: "station-label", offset: [5, 0] }) : undefined,
    });
  }
  function addSpeedLegend() {
    const legend = $("legend");
    legend.innerHTML = '<div class="legend-title">铁路行程</div><div class="legend-row"><i class="swatch route-swatch route-swatch--highspeed" aria-hidden="true"></i><span>高铁 / 动车</span></div><div class="legend-row"><i class="swatch route-swatch route-swatch--conventional" aria-hidden="true"></i><span>普速铁路</span></div><div class="legend-title speed-legend-title">设计速度 / 最高速度</div>' + Object.keys(speedLabels).map((key) => `<div class="legend-row"><i class="swatch" style="background:${speedColors[key]}"></i><span>${speedLabels[key]}</span></div>`).join("");
  }
  function refresh() {
    const showAllRoutes = $("visited").checked;
    const showHighspeedRoutes = showAllRoutes || $("visitedHighspeed").checked;
    const showConventionalRoutes = showAllRoutes || $("visitedConventional").checked;
    const visibleRoute = (feature) => {
      if (!selectedRouteIds.has(Number(feature.properties.seq))) return false;
      return (feature.properties.service === "highspeed" && showHighspeedRoutes)
        || (feature.properties.service === "conventional" && showConventionalRoutes);
    };
    Object.values(layers).forEach((layer) => map.removeLayer(layer));
    layers.provinces.addTo(map);
    if ($("cityBounds").checked && layers.cities) layers.cities.addTo(map);
    if (layers.provinceBoundaries) layers.provinceBoundaries.addTo(map);
    if (routeData) {
      const routeCities = new Set((routeData?.features || []).filter(visibleRoute).flatMap((feature) => [feature.properties.origin_city, feature.properties.destination_city]).filter(Boolean));
      layers.railCities = geojson(railCitiesData, { filter: (feature) => routeCities.has(feature.properties.display), style: styleVisitedCity });
      layers.railCityLabels = addCityLabels(railCityLabelsData, "city-label", (feature) => routeCities.has(feature.properties.display));
    }
    if (($("network").checked || $("speedNetwork").checked) && layers.network) {
      layers.network.setStyle((feature) => $("speedNetwork").checked
        ? { pane: "railNetwork", color: speedColors[feature.properties.speed_class] || speedColors.unknown, weight: 1.05, opacity: .72 }
        : { pane: "railNetwork", color: "#aab5b1", weight: .75, opacity: .68 });
      layers.network.addTo(map);
    }
    if (routeData) {
      layers.routeOuter = geojson(routeData, {
        filter: visibleRoute,
        style: (feature) => routeStyle(feature.properties.service, "outer"),
      });
      layers.routeInner = geojson(routeData, {
        filter: visibleRoute,
        style: (feature) => routeStyle(feature.properties.service, "inner"),
        onEachFeature: routePopup,
      });
      if (showHighspeedRoutes || showConventionalRoutes) {
        layers.routeOuter.addTo(map);
        layers.routeInner.addTo(map);
      }
    }
    updateZoomDependentLayers();
  }
  function updateZoomDependentLayers() {
    const zoom = map.getZoom();
    if (($('network').checked || $('speedNetwork').checked) && zoom >= 9 && !layers.networkStations) {
      ensureNetworkStations().then(updateZoomDependentLayers).catch((error) => console.error(error));
    }
    [layers.railCities, layers.railCityLabels, layers.otherCities, layers.otherCityLabels, layers.networkStations, layers.networkStationLabels, layers.highspeedStations, layers.conventionalStations].forEach((layer) => { if (layer) map.removeLayer(layer); });
    if ($("visitedCities").checked && zoom >= 5 && layers.railCities) {
      layers.railCities.addTo(map);
      layers.railCityLabels.addTo(map);
    }
    if ($("otherVisitedCities").checked && zoom >= 5 && layers.otherCities && layers.otherCityLabels) {
      layers.otherCities.addTo(map);
      layers.otherCityLabels.addTo(map);
    }
    const showAllRoutes = $("visited").checked;
    const showHighspeedRoutes = showAllRoutes || $("visitedHighspeed").checked;
    const showConventionalRoutes = showAllRoutes || $("visitedConventional").checked;
    const visibleRoutes = (routeData?.features || []).filter((feature) =>
      selectedRouteIds.has(Number(feature.properties.seq))
      && ((feature.properties.service === "highspeed" && showHighspeedRoutes)
        || (feature.properties.service === "conventional" && showConventionalRoutes))
    );
    const stationNames = new Set(visibleRoutes.flatMap((feature) => [feature.properties.origin, feature.properties.destination]));
    if (visitedStationsData) {
      layers.highspeedStations = addStations(visitedStationsData, "highspeed", true, true, stationNames);
      layers.conventionalStations = addStations(visitedStationsData, "conventional", true, true, stationNames);
    }
    const routeSubset = selectedRouteIds.size < (routeData?.features.length || 0);
    if (!routeSubset && ($("network").checked || $("speedNetwork").checked) && zoom >= 9 && layers.networkStations) layers.networkStations.addTo(map);
    if (!routeSubset && ($("network").checked || $("speedNetwork").checked) && zoom >= 12 && layers.networkStationLabels) layers.networkStationLabels.addTo(map);
    if (zoom >= 7 && showHighspeedRoutes && layers.highspeedStations) layers.highspeedStations.addTo(map);
    if (zoom >= 7 && showConventionalRoutes && layers.conventionalStations) layers.conventionalStations.addTo(map);
  }
  function routePopup(feature, layer) {
    const p = feature.properties;
    layer.bindTooltip(`${p.train || ""} · ${p.origin || ""}—${p.destination || ""} · ${p.table_km || 0} km`, { sticky: true, className: "route-tooltip" });
  }
  function renderRouteList() {
    if (!routeData) {
      $("routeList").innerHTML = '<div class="note">行程数据加载中…</div>';
      return;
    }
    const query = $("routeSearch").value.trim().toLowerCase();
    const rows = routeData.features.filter((feature) => {
      const p = feature.properties;
      return `${p.train} ${p.origin} ${p.destination}`.toLowerCase().includes(query);
    });
    $("routeList").innerHTML = rows.map((feature) => {
      const p = feature.properties;
      const id = Number(p.seq);
      const details = [p.date || "日期未录入", p.time || "时间未录入", `${p.table_km || 0} km`];
      return `<label class="route-option"><input type="checkbox" data-route-id="${id}"${selectedRouteIds.has(id) ? " checked" : ""}><span class="route-option-main"><strong><span class="route-train">${p.train}</span><span class="route-journey">${p.origin}—${p.destination}</span></strong><small class="route-meta">${details.map((value) => `<span>${value}</span>`).join("")}</small></span></label>`;
    }).join("") || '<div class="note">没有匹配的路线</div>';
  }
  Promise.all([load("provinces"), load("province_boundaries"), load("rail_visited_cities"), load("rail_city_labels")]).then(([provinces, provinceBoundaries, railCities, railCityLabels]) => {
    layers.provinces = geojson(provinces, { style: styleProvince });
    layers.provinceBoundaries = geojson(provinceBoundaries, { style: styleProvinceBoundary });
    railCitiesData = railCities;
    railCityLabelsData = railCityLabels;
    layers.provinces.addTo(map);
    addSpeedLegend();
    refresh();
    map.fitBounds(bounds, { padding: [12, 12] });
    renderRouteList();
    Promise.all([load("city_boundaries"), load("other_visited_cities"), load("other_city_labels")]).then(([cityBoundaries, otherCities, otherCityLabels]) => {
      layers.cities = geojson(cityBoundaries, { style: styleCities });
      layers.otherCities = geojson(otherCities, { style: styleOtherVisitedCity });
      layers.otherCityLabels = addCityLabels(otherCityLabels, "other-city-label");
      refresh();
    });
    return Promise.all([load("visited_routes"), load("visited_stations")]);
  }).then((routePayload) => {
    if (!routePayload) return;
    const [routes, stations] = routePayload;
    routeData = routes;
    routeData.features.forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq)));
    visitedStationsData = stations;
    refresh();
    renderRouteList();
  }).catch((error) => { console.error(error); });
  ["visited", "visitedHighspeed", "visitedConventional", "cityBounds", "visitedCities", "otherVisitedCities"].forEach((id) => $(id).addEventListener("change", refresh));
  ["network", "speedNetwork"].forEach((id) => $(id).addEventListener("change", async (event) => {
    if (event.target.checked) {
      try {
        await ensureNetworkLayers();
      } catch (error) {
        event.target.checked = false;
        console.error(error);
      }
    }
    refresh();
  }));
  $("reset").addEventListener("click", () => map.fitBounds(bounds, { padding: [12, 12] }));
  $("routeSearch").addEventListener("input", renderRouteList);
  $("routeList").addEventListener("change", (event) => { const id = Number(event.target.dataset.routeId); if (!Number.isFinite(id)) return; if (event.target.checked) selectedRouteIds.add(id); else selectedRouteIds.delete(id); renderRouteList(); refresh(); });
  $("selectAllRoutes").addEventListener("click", () => { routeData?.features.forEach((feature) => selectedRouteIds.add(Number(feature.properties.seq))); renderRouteList(); refresh(); });
  $("clearRoutes").addEventListener("click", () => { selectedRouteIds.clear(); renderRouteList(); refresh(); });
  map.on("zoomend", updateZoomDependentLayers);
})();
