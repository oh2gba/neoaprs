/* The PulseAudio backend of Mercury's audio layer, replaced by nothing: scripts/build-mercury copies this file over audioio/ffaudio/ffaudio/pulse.c in the unpacked source before it builds, so that the program does not link
 * libpulse and its two dozen libraries and the bundle holds one sound library, ALSA (Mercury's default on Linux; PulseAudio and PipeWire both offer an ALSA device to it). Mercury's Makefile compiles pulse.c and refers to
 * `ffpulse` whatever the build asks, so the interface has to exist; it fails at init, the one call Mercury makes before anything else of it, with a message that reaches the log, and every other function is a no-op that
 * returns what the interface documents for a failure (audio.h), so that a call that does come is harmless. Designated initialisers: a member renamed or added in a newer ffaudio fails the compile loudly at a version bump instead
 * of shifting the others by one place. */

#include <ffaudio/audio.h>

#define STUB_MESSAGE "PulseAudio is not in this build of Mercury (NeoAPRS uses ALSA)"

static int stub_init(ffaudio_init_conf *conf)
{
	if (conf != NULL)
		conf->error = STUB_MESSAGE;
	return FFAUDIO_ERROR;
}

static void stub_uninit(void)
{
}

static ffaudio_dev* stub_dev_alloc(unsigned mode)
{
	(void) mode;
	return NULL;
}

static void stub_dev_free(ffaudio_dev *d)
{
	(void) d;
}

static const char* stub_dev_error(ffaudio_dev *d)
{
	(void) d;
	return STUB_MESSAGE;
}

static int stub_dev_next(ffaudio_dev *d)
{
	(void) d;
	return -FFAUDIO_ERROR;
}

static const char* stub_dev_info(ffaudio_dev *d, unsigned i)
{
	(void) d;
	(void) i;
	return NULL;
}

static ffaudio_buf* stub_alloc(void)
{
	return NULL;
}

static void stub_free(ffaudio_buf *b)
{
	(void) b;
}

static const char* stub_error(ffaudio_buf *b)
{
	(void) b;
	return STUB_MESSAGE;
}

static int stub_open(ffaudio_buf *b, ffaudio_conf *conf, unsigned flags)
{
	(void) b;
	(void) conf;
	(void) flags;
	return FFAUDIO_ERROR;
}

static int stub_start(ffaudio_buf *b)
{
	(void) b;
	return FFAUDIO_ERROR;
}

static int stub_stop(ffaudio_buf *b)
{
	(void) b;
	return FFAUDIO_ERROR;
}

static int stub_clear(ffaudio_buf *b)
{
	(void) b;
	return FFAUDIO_ERROR;
}

static int stub_write(ffaudio_buf *b, const void *data, size_t len)
{
	(void) b;
	(void) data;
	(void) len;
	return -FFAUDIO_ERROR;
}

static int stub_drain(ffaudio_buf *b)
{
	(void) b;
	return -FFAUDIO_ERROR;
}

static int stub_read(ffaudio_buf *b, const void **buffer)
{
	(void) b;
	if (buffer != NULL)
		*buffer = NULL;
	return -FFAUDIO_ERROR;
}

static void stub_signal(ffaudio_buf *b)
{
	(void) b;
}

const ffaudio_interface ffpulse = {
	.init = stub_init,
	.uninit = stub_uninit,
	.dev_alloc = stub_dev_alloc,
	.dev_free = stub_dev_free,
	.dev_error = stub_dev_error,
	.dev_next = stub_dev_next,
	.dev_info = stub_dev_info,
	.alloc = stub_alloc,
	.free = stub_free,
	.error = stub_error,
	.open = stub_open,
	.start = stub_start,
	.stop = stub_stop,
	.clear = stub_clear,
	.write = stub_write,
	.drain = stub_drain,
	.read = stub_read,
	.signal = stub_signal,
};
