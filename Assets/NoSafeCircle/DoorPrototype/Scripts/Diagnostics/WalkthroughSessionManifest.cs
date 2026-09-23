using System;
using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Diagnostics
{
    /// <summary>
    /// What a walkthrough captured, when, and where the player was standing for each
    /// frame. Written as <c>session.json</c> beside the PNGs.
    /// </summary>
    /// <remarks>
    /// The per-frame position is the field that makes the folder answer a question.
    /// Without it a reviewer can say "frame 47 shows bare floor" and nothing more;
    /// with it the same frame reports a world position inside a named scene, which is
    /// a defect someone can act on without asking the player where they were.
    /// <para>
    /// Deliberate exception to the "avoid public mutable fields" rule in the
    /// engineering standards: <see cref="JsonUtility"/> serializes public fields and
    /// ignores properties, so this type is a serialization shape rather than an API.
    /// Nothing outside the capture path should hold one after it is written.
    /// </para>
    /// </remarks>
    [Serializable]
    public class WalkthroughSessionManifest
    {
        /// <summary>One captured frame, matching <c>ScreenshotNNNNNN.png</c> by index.</summary>
        [Serializable]
        public class FrameRecord
        {
            public int index;
            public string capturedUtc;
            public string sceneName;

            /// <summary>
            /// False when no player component was present, so a reader can tell an
            /// origin-because-absent position from a genuine position at the origin.
            /// </summary>
            public bool playerResolved;

            public Vector3 playerPosition;
            public bool cameraResolved;
            public Vector3 cameraPosition;
            public float cameraOrthographicSize;
        }

        /// <summary>A frame the player flagged during the walkthrough.</summary>
        [Serializable]
        public class Mark
        {
            public int frameIndex;
            public string markedUtc;
            public string note;
        }

        public string startedUtc;
        public string endedUtc;
        public string unityVersion;
        public string applicationVersion;

        /// <summary>Commit the build came from when a build stamp is present; otherwise empty.</summary>
        public string buildCommit;

        public string startSceneName;
        public float framesPerSecond;
        public float scale;
        public int frameWidth;
        public int frameHeight;
        public int framesCaptured;

        /// <summary>
        /// Frames the writer refused because its queue was full. Non-zero means the
        /// walkthrough has gaps, and the reader should not read a gap as a still camera.
        /// </summary>
        public int framesDroppedByBackPressure;

        /// <summary>
        /// Frames still queued when the session ended. Non-zero means PNGs named in
        /// <see cref="frames"/> may be missing from disk.
        /// </summary>
        public int framesUnwrittenAtShutdown;

        /// <summary>Frames accepted and queued that never reached disk.</summary>
        public int framesFailedToWrite;

        public List<FrameRecord> frames = new List<FrameRecord>();
        public List<Mark> marks = new List<Mark>();
    }
}
