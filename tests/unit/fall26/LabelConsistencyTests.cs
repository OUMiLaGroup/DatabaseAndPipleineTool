// LabelConsistencyTests.cs
//
// C# port of the label consistency demonstration test.
// Uses xUnit, the standard .NET unit testing framework.
//
// Run with:
//   dotnet test
// (requires the accompanying LabelConsistencyTests.csproj and the
// Microsoft.NET.Test.Sdk / xunit / xunit.runner.visualstudio packages,
// which `dotnet restore` will pull down automatically)

using System;
using System.Collections.Generic;
using System.Linq;
using Xunit;

namespace OpenPilotPipeline.Tests
{
    // -----------------------------------------------------------------------
    // A minimal stand-in for a real detection record coming out of CVAT / a model
    // -----------------------------------------------------------------------
    public class Detection
    {
        public string ObjectType { get; set; } = "";  // e.g. "pedestrian", "car", "cyclist", "truck"
        public double WidthM { get; set; }              // bounding box width in meters
        public double HeightM { get; set; }              // bounding box height in meters
        public double LengthM { get; set; }              // bounding box length in meters
        public double Confidence { get; set; }           // model confidence score, 0.0 - 1.0

        public Detection(string objectType, double widthM, double heightM, double lengthM, double confidence)
        {
            ObjectType = objectType;
            WidthM = widthM;
            HeightM = heightM;
            LengthM = lengthM;
            Confidence = confidence;
        }
    }

    // -----------------------------------------------------------------------
    // Core validation logic
    // -----------------------------------------------------------------------
    public static class LabelConsistencyChecker
    {
        private const double MinConfidence = 0.5;

        // Expected "reasonable" dimension ranges per object class (min, max) in meters.
        // These are rough, illustrative numbers -- not real-world engineering specs.
        public static readonly Dictionary<string, Dictionary<string, (double Low, double High)>> ExpectedDimensions =
            new()
            {
                ["pedestrian"] = new() { ["width"] = (0.3, 1.0), ["height"] = (1.2, 2.2), ["length"] = (0.3, 1.0) },
                ["cyclist"]    = new() { ["width"] = (0.4, 1.0), ["height"] = (1.2, 2.2), ["length"] = (1.5, 2.2) },
                ["car"]        = new() { ["width"] = (1.5, 2.2), ["height"] = (1.3, 1.9), ["length"] = (3.5, 5.5) },
                ["truck"]      = new() { ["width"] = (2.0, 3.0), ["height"] = (2.5, 4.5), ["length"] = (6.0, 16.0) },
            };

        /// <summary>
        /// Compare a detection's dimensions/confidence against the expected
        /// ranges for its labeled ObjectType.
        ///
        /// Returns a list of human-readable issue strings. An empty list
        /// means the detection looks consistent.
        /// </summary>
        public static List<string> FlagDetectionIssues(Detection detection)
        {
            var issues = new List<string>();

            if (!ExpectedDimensions.TryGetValue(detection.ObjectType, out var expected))
            {
                issues.Add($"Unknown ObjectType '{detection.ObjectType}' - no size rules defined");
                return issues;
            }

            foreach (var (dimName, range) in expected)
            {
                double value = dimName switch
                {
                    "width" => detection.WidthM,
                    "height" => detection.HeightM,
                    "length" => detection.LengthM,
                    _ => throw new InvalidOperationException($"Unhandled dimension '{dimName}'"),
                };

                if (value < range.Low || value > range.High)
                {
                    issues.Add(
                        $"{dimName} of {value}m is outside expected range " +
                        $"[{range.Low}, {range.High}]m for ObjectType '{detection.ObjectType}'");
                }
            }

            if (detection.Confidence < MinConfidence)
            {
                issues.Add($"confidence {detection.Confidence} is below minimum threshold {MinConfidence}");
            }

            return issues;
        }
    }

    // -----------------------------------------------------------------------
    // Unit tests
    // -----------------------------------------------------------------------
    public class LabelConsistencyTests
    {
        [Fact]
        public void NormalPedestrian_HasNoIssues()
        {
            var detection = new Detection("pedestrian", widthM: 0.5, heightM: 1.7, lengthM: 0.5, confidence: 0.91);
            var issues = LabelConsistencyChecker.FlagDetectionIssues(detection);
            Assert.Empty(issues);
        }

        [Fact]
        public void OversizedPedestrian_IsFlagged()
        {
            // Same "pedestrian" label, but dimensions look more like a car.
            var detection = new Detection("pedestrian", widthM: 1.9, heightM: 1.6, lengthM: 4.5, confidence: 0.88);
            var issues = LabelConsistencyChecker.FlagDetectionIssues(detection);
            Assert.NotEmpty(issues);
        }

        [Fact]
        public void NormalCar_HasNoIssues()
        {
            var detection = new Detection("car", widthM: 1.8, heightM: 1.5, lengthM: 4.6, confidence: 0.95);
            var issues = LabelConsistencyChecker.FlagDetectionIssues(detection);
            Assert.Empty(issues);
        }

        [Fact]
        public void UndersizedCar_IsFlagged()
        {
            // Label says "car" but the box is pedestrian-sized.
            var detection = new Detection("car", widthM: 0.5, heightM: 1.7, lengthM: 0.6, confidence: 0.80);
            var issues = LabelConsistencyChecker.FlagDetectionIssues(detection);
            Assert.NotEmpty(issues);
        }

        [Fact]
        public void LowConfidence_IsFlagged()
        {
            var detection = new Detection("cyclist", widthM: 0.6, heightM: 1.7, lengthM: 1.8, confidence: 0.20);
            var issues = LabelConsistencyChecker.FlagDetectionIssues(detection);
            Assert.Contains(issues, issue => issue.Contains("confidence"));
        }

        [Fact]
        public void UnknownObjectType_IsFlagged()
        {
            var detection = new Detection("traffic_cone", widthM: 0.3, heightM: 0.7, lengthM: 0.3, confidence: 0.9);
            var issues = LabelConsistencyChecker.FlagDetectionIssues(detection);
            Assert.Contains(issues, issue => issue.Contains("Unknown ObjectType"));
        }
    }
}
