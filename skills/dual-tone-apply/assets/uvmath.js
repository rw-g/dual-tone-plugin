/* UV adjustment math shared by the live preview and the baked download (also unit-tested under node).
   All four controls act on the PICTURE as seen on the model (u right, v up; 3MF origin bottom-left):
     rotation  : degrees, positive = picture turns counter-clockwise, about the texture centre (0.5, 0.5)  (the "w" axis, out of the surface)
     du, dv    : picture moves by (du, dv) in texture units (positive u = toward +u / to the right)
     scale     : picture size on the surface (2 = twice as large); clamped to >= 0.01
   Sampling coordinate for a surface UV:   uv' = c + A (uv - c - t),   A = (1/s) R(-theta),   c = (0.5, 0.5),  t = (du, dv)           */
function uvAffine(st) {
  var s = Math.max(Number(st.scale), 0.01), th = Number(st.rot) * Math.PI / 180, cs = Math.cos(th), sn = Math.sin(th), k = 1 / s;
  var a = k * cs, b = k * sn, c = -k * sn, d = k * cs;                       // A = k * R(-theta) = k * [[cos, sin], [-sin, cos]]
  var du = Number(st.du), dv = Number(st.dv);
  var tx = 0.5 - (a * (0.5 + du) + b * (0.5 + dv)), ty = 0.5 - (c * (0.5 + du) + d * (0.5 + dv));   // c - A (c + t)
  return [a, b, tx, c, d, ty];                                                // row-major 2x3: u' = a u + b v + tx ; v' = c u + d v + ty
}
function uvApply(m, u, v) { return [m[0] * u + m[1] * v + m[2], m[3] * u + m[4] * v + m[5]]; }
function uvIsIdentity(st) { return Math.abs(st.rot) < 1e-9 && Math.abs(st.du) < 1e-9 && Math.abs(st.dv) < 1e-9 && Math.abs(st.scale - 1) < 1e-9; }

// ---- projections. frame = { pos:[x,y,z], rot:[9 numbers, row-major world->local rotation], size:[sx,sy,sz] }; local = rot * (p - pos).
// planar: look along local -Z, u = x/sx+.5, v = y/sy+.5 | cylindrical: axis = local Z, u = angle/2pi+.5 (increases to the right seen from outside), v = z/sz+.5
// spherical: u as cylindrical, v = latitude/pi+.5 | box: the face normal's dominant local axis picks one of six planar projections, upright and not mirrored seen from outside.
function _loc(fr, p) {
  var x = p[0] - fr.pos[0], y = p[1] - fr.pos[1], z = p[2] - fr.pos[2], r = fr.rot;
  return [r[0] * x + r[1] * y + r[2] * z, r[3] * x + r[4] * y + r[5] * z, r[6] * x + r[7] * y + r[8] * z];
}
function _safe(s) { s = Math.abs(Number(s)); return s < 1e-9 ? 1e-9 : s; }
function projectTriangle(type, fr, tri) {
  // tri = [[x,y,z] x3] in world space -> [u0,v0,u1,v1,u2,v2]
  var sx = _safe(fr.size[0]), sy = _safe(fr.size[1]), sz = _safe(fr.size[2]), L = tri.map(function (p) { return _loc(fr, p); }), out = [], i;
  if (type === 'planar') {
    for (i = 0; i < 3; i++) out.push(L[i][0] / sx + 0.5, L[i][1] / sy + 0.5);
  } else if (type === 'box') {
    var a = [L[1][0] - L[0][0], L[1][1] - L[0][1], L[1][2] - L[0][2]], b = [L[2][0] - L[0][0], L[2][1] - L[0][1], L[2][2] - L[0][2]];
    var n = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]], ax = Math.abs(n[0]), ay = Math.abs(n[1]), az = Math.abs(n[2]);
    for (i = 0; i < 3; i++) {
      var x = L[i][0], y = L[i][1], z = L[i][2];
      if (az >= ax && az >= ay) out.push(n[2] >= 0 ? x / sx + 0.5 : -x / sx + 0.5, y / sy + 0.5);
      else if (ax >= ay) out.push(n[0] >= 0 ? y / sy + 0.5 : -y / sy + 0.5, z / sz + 0.5);
      else out.push(n[1] >= 0 ? -x / sx + 0.5 : x / sx + 0.5, z / sz + 0.5);
    }
  } else {                                                  // cylindrical | spherical
    var us = [], on = [], u0 = null;
    for (i = 0; i < 3; i++) {
      var q = L[i], onAxis = q[0] * q[0] + q[1] * q[1] < 1e-18; on.push(onAxis);
      us.push(onAxis ? null : Math.atan2(q[1], q[0]) / (2 * Math.PI) + 0.5);
      if (u0 === null && !onAxis) u0 = us[i];
    }
    if (u0 === null) u0 = 0.5;
    for (i = 0; i < 3; i++) if (us[i] !== null) us[i] += Math.round(u0 - us[i]);     // keep the triangle continuous across the seam
    var known = us.filter(function (u) { return u !== null; }), mean = known.length ? known.reduce(function (s, u) { return s + u; }, 0) / known.length : 0.5;
    for (i = 0; i < 3; i++) {
      var u = us[i] === null ? mean : us[i], v;
      if (type === 'cylindrical') v = L[i][2] / sz + 0.5;
      else { var r = Math.sqrt(L[i][0] * L[i][0] + L[i][1] * L[i][1] + L[i][2] * L[i][2]); v = r < 1e-12 ? 0.5 : Math.asin(Math.max(-1, Math.min(1, L[i][2] / r))) / Math.PI + 0.5; }
      out.push(u, v);
    }
  }
  return out;
}
if (typeof module !== 'undefined' && module.exports) module.exports = { uvAffine: uvAffine, uvApply: uvApply, uvIsIdentity: uvIsIdentity, projectTriangle: projectTriangle };
