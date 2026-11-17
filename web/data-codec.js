/* Exact inverse of railway_web/build_startup_data.py. */
((global) => {
  function unpack(payload) {
    if (payload.format !== 'rail-map-1') throw new Error('Unsupported railway data format');
    const decoded = new Map();
    function arc(index) {
      if (decoded.has(index)) return decoded.get(index);
      const encoded = payload.arcs[index];
      const points = [];
      let offset = 0;
      let x = 0;
      let y = 0;
      function delta() {
        let value = 0;
        let shift = 0;
        let byte;
        do {
          byte = encoded.charCodeAt(offset++) - 63;
          value |= (byte & 31) << shift;
          shift += 5;
        } while (byte >= 32);
        return value & 1 ? ~(value >>> 1) : value >>> 1;
      }
      while (offset < encoded.length) {
        x += delta(); y += delta();
        points.push([x / payload.precision, y / payload.precision]);
      }
      decoded.set(index, points);
      return points;
    }
    function path(references) {
      const points = [];
      for (const reference of references) {
        const segment = reference < 0 ? arc(~reference).slice().reverse() : arc(reference);
        for (let index = points.length ? 1 : 0; index < segment.length; index++) points.push(segment[index]);
      }
      return points;
    }
    function geometry(item) {
      if (item.type === 'GeometryCollection') return { ...item, geometries: item.geometries.map(geometry) };
      if (!item.arcs) return item;
      const depths = { LineString: 0, MultiLineString: 1, Polygon: 1, MultiPolygon: 2 };
      const nest = (coordinates, depth) => depth === 0 ? path(coordinates) : coordinates.map((part) => nest(part, depth - 1));
      const { arcs, ...result } = item;
      return { ...result, coordinates: nest(arcs, depths[item.type]) };
    }
    return Object.fromEntries(Object.entries(payload.layers).map(([name, collection]) => [name, {
      ...collection, features: collection.features.map((feature) => ({ ...feature, geometry: geometry(feature.geometry) })),
    }]));
  }
  global.RailMapData = { unpack };
  if (typeof module !== 'undefined') module.exports = { unpack };
})(typeof window === 'undefined' ? globalThis : window);
