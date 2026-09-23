using System;
using System.Collections.Concurrent;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace NoSafeCircle.DoorPrototype.Diagnostics
{
    /// <summary>
    /// Owns PNG encoding and disk writing for one walkthrough session, off the main
    /// thread, and owns the background task doing it.
    /// </summary>
    /// <remarks>
    /// Encoding and writing a frame costs more than the frame budget, so doing it
    /// inline would stutter the game. That matters beyond comfort: a capture that
    /// changes the frame rate changes the thing it is supposed to be observing.
    /// <para>
    /// A <see cref="Texture2D"/> cannot be touched from a worker thread, which is why
    /// this takes raw bytes: <see cref="ImageConversion.EncodeArrayToPNG"/> accepts a
    /// byte array plus a format and dimensions, and is safe to call here.
    /// </para>
    /// <para>
    /// The queue is bounded. An unbounded one grows without limit whenever encoding
    /// falls behind capture, which at full resolution is tens of megabytes per second
    /// and eventually the session. Refusing a frame and counting the refusal is worse
    /// for the walkthrough and much better for the process, and the count reaches the
    /// manifest so a reader can see the gap rather than misread it as a still camera.
    /// </para>
    /// </remarks>
    public sealed class WalkthroughFrameWriter : IDisposable
    {
        private const int IdleSleepMilliseconds = 10;

        /// <summary>Cap on the blocking wait in <see cref="Dispose"/>, which runs during teardown.</summary>
        private static readonly TimeSpan DisposeDrainTimeout = TimeSpan.FromSeconds(5d);

        private readonly struct PendingFrame
        {
            public readonly byte[] Pixels;
            public readonly int Width;
            public readonly int Height;
            public readonly string Path;

            public PendingFrame(byte[] pixels, int width, int height, string path)
            {
                Pixels = pixels;
                Width = width;
                Height = height;
                Path = path;
            }
        }

        private readonly ConcurrentQueue<PendingFrame> pending = new ConcurrentQueue<PendingFrame>();
        private readonly int maximumQueuedFrames;
        private readonly Task worker;

        private volatile bool stopRequested;
        private int queuedCount;
        private int droppedCount;
        private bool disposed;

        /// <summary>Frames accepted but not yet written.</summary>
        public int QueuedCount => Volatile.Read(ref queuedCount);

        /// <summary>Frames refused because the queue was full.</summary>
        public int DroppedCount => Volatile.Read(ref droppedCount);

        public WalkthroughFrameWriter(int maximumQueuedFrames)
        {
            if (maximumQueuedFrames <= 0)
            {
                throw new ArgumentOutOfRangeException(
                    nameof(maximumQueuedFrames), maximumQueuedFrames,
                    "A walkthrough writer needs room for at least one frame.");
            }

            this.maximumQueuedFrames = maximumQueuedFrames;
            worker = Task.Run((Action)ProcessQueue);
        }

        /// <summary>
        /// Hand one frame to the writer. Returns false when back pressure refused it,
        /// so the caller can leave the frame index unconsumed and keep filenames and
        /// manifest entries in step with the PNGs that actually exist.
        /// </summary>
        public bool TryEnqueue(byte[] pixels, int width, int height, string path)
        {
            if (pixels == null)
            {
                throw new ArgumentNullException(nameof(pixels));
            }

            if (string.IsNullOrEmpty(path))
            {
                throw new ArgumentException("A frame needs a destination path.", nameof(path));
            }

            if (disposed || stopRequested)
            {
                throw new InvalidOperationException("This walkthrough writer has stopped accepting frames.");
            }

            if (Volatile.Read(ref queuedCount) >= maximumQueuedFrames)
            {
                Interlocked.Increment(ref droppedCount);
                return false;
            }

            Interlocked.Increment(ref queuedCount);
            pending.Enqueue(new PendingFrame(pixels, width, height, path));
            return true;
        }

        /// <summary>
        /// Stop accepting frames and write everything already queued. Returns the
        /// number still unwritten when <paramref name="timeout"/> expired, which is
        /// zero on a clean finish.
        /// </summary>
        /// <remarks>
        /// This blocks the caller. At a walkthrough's cadence the queue is normally
        /// empty and it returns at once; the timeout exists so a stalled disk cannot
        /// hang the editor rather than because waiting is expected.
        /// </remarks>
        public int CompleteWriting(TimeSpan timeout)
        {
            if (disposed)
            {
                return QueuedCount;
            }

            stopRequested = true;

            try
            {
                worker.Wait(timeout);
            }
            catch (AggregateException exception)
            {
                Debug.LogError("Walkthrough frame writer failed while draining: " + exception);
            }

            return QueuedCount;
        }

        public void Dispose()
        {
            if (disposed)
            {
                return;
            }

            disposed = true;
            stopRequested = true;

            try
            {
                worker.Wait(DisposeDrainTimeout);
            }
            catch (AggregateException exception)
            {
                Debug.LogError("Walkthrough frame writer failed during disposal: " + exception);
            }
        }

        private void ProcessQueue()
        {
            while (true)
            {
                if (pending.TryDequeue(out PendingFrame frame))
                {
                    WriteFrame(frame);
                    continue;
                }

                // Only leave once the queue is drained, so a stop never discards the
                // tail of a session that was captured but not yet on disk.
                if (stopRequested)
                {
                    return;
                }

                Thread.Sleep(IdleSleepMilliseconds);
            }
        }

        private void WriteFrame(PendingFrame frame)
        {
            try
            {
                byte[] png = ImageConversion.EncodeArrayToPNG(
                    frame.Pixels,
                    GraphicsFormat.R8G8B8_UNorm,
                    (uint)frame.Width,
                    (uint)frame.Height);

                if (png == null || png.Length == 0)
                {
                    Debug.LogError("Walkthrough frame encoded to nothing: " + frame.Path);
                    return;
                }

                File.WriteAllBytes(frame.Path, png);
            }
            catch (Exception exception)
            {
                // One unwritable frame must not take the session down with it.
                Debug.LogError("Walkthrough frame was not written to " + frame.Path + ": " + exception);
            }
            finally
            {
                Interlocked.Decrement(ref queuedCount);
            }
        }
    }
}
