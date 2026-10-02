// SPDX-License-Identifier: MIT
// Copyright (c) 2021 x-io Technologies
// Copyright (c) 2026 Brickwright contributors
// Adapted from FusionAhrs.c (HalfGravity, Residual, inclination feedback),
// xioTechnologies/Fusion@a8d7224f36a0ec82345ef49a3db50e65f8d3bab8.
// Full grant: licenses/Fusion-MIT.txt in the firmware repository root.
using System.Numerics;

namespace ImuViewer.Core.Filters;

/// <summary>
/// Six-axis orientation using MIT-licensed Fusion gravity-vector feedback.
/// Historical class/property names are retained for caller compatibility.
/// This is a reduced adapter with exponential quaternion integration; it
/// omits Fusion's startup, magnetic feedback and rejection state.
/// Beta maps to proportional gain as 10 * Beta, not the old gradient gain.
/// Firmware uses the same equations with its existing stationary gate.
/// </summary>
public sealed class MadgwickFilter : IOrientationFilter
{
    private Quaternion _orientation = Quaternion.Identity;
    public float Beta { get; set; } = 0.05f;
    public Quaternion Orientation => _orientation;
    public void Reset() => _orientation = Quaternion.Identity;

    public void Update(Vector3 accelG, Vector3 gyroRadS, float dt)
    {
        if (!float.IsFinite(dt) || dt <= 0 || !float.IsFinite(Beta) || Beta < 0 ||
            !Finite(accelG) || !Finite(gyroRadS))
            return;

        Quaternion q = _orientation;
        Vector3 rate = gyroRadS;
        float norm = accelG.Length();
        if (norm > 1e-6f)
        {
            Vector3 sensor = accelG / norm;
            Vector3 halfGravity = new(q.X * q.Z - q.W * q.Y,
                                     q.Y * q.Z + q.W * q.X,
                                     q.W * q.W + q.Z * q.Z - 0.5f);
            Vector3 residual = Vector3.Cross(sensor, halfGravity);
            if (Vector3.Dot(sensor, halfGravity) <= 0 && residual.Length() > 1e-6f)
                residual = Vector3.Normalize(residual);
            rate += 20f * Beta * residual;
        }

        float speed = rate.Length();
        float angle = 0.5f * speed * dt;
        float scale = speed > 1e-6f ? MathF.Sin(angle) / speed : 0.5f * dt;
        Quaternion increment = new(rate * scale, MathF.Cos(angle));
        Quaternion next = q * increment;
        float length = next.Length();
        if (float.IsFinite(length) && length > 1e-6f)
            _orientation = Quaternion.Normalize(next);
    }

    private static bool Finite(Vector3 v) =>
        float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z);
}
