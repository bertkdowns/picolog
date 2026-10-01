#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct libusb_device_handle libusb_device_handle;
#define LIBUSB_ENDPOINT_IN 0x80

struct libusb_transfer;
typedef void (*libusb_transfer_cb_fn)(struct libusb_transfer *transfer);
struct libusb_transfer {
    libusb_device_handle *dev_handle;
    uint8_t flags;
    unsigned char endpoint;
    unsigned char type;
    unsigned int timeout;
    int status;
    int length;
    int actual_length;
    libusb_transfer_cb_fn callback;
    void *user_data;
    unsigned char *buffer;
    int num_iso_packets;
};

struct callback_context {
    libusb_transfer_cb_fn callback;
    void *user_data;
};

static pthread_mutex_t trace_lock = PTHREAD_MUTEX_INITIALIZER;

static void dump(const unsigned char *data, int length) {
    for (int i = 0; i < length; i++)
        fprintf(stderr, "%02x", data[i]);
}

static void trace_callback(struct libusb_transfer *transfer) {
    struct callback_context *context = transfer->user_data;
    pthread_mutex_lock(&trace_lock);
    fprintf(stderr,
            "USB async complete endpoint=%02x status=%d requested=%d "
            "transferred=%d data=",
            transfer->endpoint, transfer->status, transfer->length,
            transfer->actual_length);
    if (transfer->buffer && transfer->actual_length > 0)
        dump(transfer->buffer, transfer->actual_length);
    fputc('\n', stderr);
    pthread_mutex_unlock(&trace_lock);

    transfer->callback = context->callback;
    transfer->user_data = context->user_data;
    free(context);
    transfer->callback(transfer);
}

int libusb_submit_transfer(struct libusb_transfer *transfer) {
    static int (*real_fn)(struct libusb_transfer *);
    if (!real_fn)
        real_fn = dlsym(RTLD_NEXT, "libusb_submit_transfer");

    pthread_mutex_lock(&trace_lock);
    fprintf(stderr, "USB async submit endpoint=%02x requested=%d data=",
            transfer->endpoint, transfer->length);
    if (!(transfer->endpoint & LIBUSB_ENDPOINT_IN) && transfer->buffer)
        dump(transfer->buffer, transfer->length);
    fputc('\n', stderr);
    pthread_mutex_unlock(&trace_lock);

    struct callback_context *context = malloc(sizeof(*context));
    if (!context)
        return -11;
    context->callback = transfer->callback;
    context->user_data = transfer->user_data;
    transfer->callback = trace_callback;
    transfer->user_data = context;
    int result = real_fn(transfer);
    if (result) {
        transfer->callback = context->callback;
        transfer->user_data = context->user_data;
        free(context);
    }
    return result;
}

int libusb_control_transfer(libusb_device_handle *dev, uint8_t request_type,
                            uint8_t request, uint16_t value, uint16_t index,
                            unsigned char *data, uint16_t length,
                            unsigned int timeout) {
    static int (*real_fn)(libusb_device_handle *, uint8_t, uint8_t, uint16_t,
                          uint16_t, unsigned char *, uint16_t, unsigned int);
    if (!real_fn)
        real_fn = dlsym(RTLD_NEXT, "libusb_control_transfer");
    int result = real_fn(dev, request_type, request, value, index, data, length,
                         timeout);
    pthread_mutex_lock(&trace_lock);
    fprintf(stderr,
            "USB control type=%02x request=%02x value=%04x index=%04x "
            "requested=%u result=%d data=",
            request_type, request, value, index, length, result);
    int captured = (request_type & LIBUSB_ENDPOINT_IN) && result > 0 ? result : length;
    if (data && captured > 0)
        dump(data, captured);
    fputc('\n', stderr);
    pthread_mutex_unlock(&trace_lock);
    return result;
}

int libusb_bulk_transfer(libusb_device_handle *dev, unsigned char endpoint,
                         unsigned char *data, int length, int *transferred,
                         unsigned int timeout) {
    static int (*real_fn)(libusb_device_handle *, unsigned char, unsigned char *,
                          int, int *, unsigned int);
    if (!real_fn)
        real_fn = dlsym(RTLD_NEXT, "libusb_bulk_transfer");
    int result = real_fn(dev, endpoint, data, length, transferred, timeout);
    int actual = transferred ? *transferred : 0;
    pthread_mutex_lock(&trace_lock);
    fprintf(stderr, "USB bulk endpoint=%02x requested=%d result=%d transferred=%d data=",
            endpoint, length, result, actual);
    int captured = (endpoint & LIBUSB_ENDPOINT_IN) ? actual : length;
    if (data && captured > 0)
        dump(data, captured);
    fputc('\n', stderr);
    pthread_mutex_unlock(&trace_lock);
    return result;
}

int libusb_claim_interface(libusb_device_handle *dev, int interface_number) {
    static int (*real_fn)(libusb_device_handle *, int);
    if (!real_fn)
        real_fn = dlsym(RTLD_NEXT, "libusb_claim_interface");
    int result = real_fn(dev, interface_number);
    fprintf(stderr, "USB claim interface=%d result=%d\n", interface_number, result);
    return result;
}

int libusb_set_interface_alt_setting(libusb_device_handle *dev,
                                     int interface_number, int alternate_setting) {
    static int (*real_fn)(libusb_device_handle *, int, int);
    if (!real_fn)
        real_fn = dlsym(RTLD_NEXT, "libusb_set_interface_alt_setting");
    int result = real_fn(dev, interface_number, alternate_setting);
    fprintf(stderr, "USB alt interface=%d setting=%d result=%d\n", interface_number,
            alternate_setting, result);
    return result;
}

int libusb_reset_device(libusb_device_handle *dev) {
    static int (*real_fn)(libusb_device_handle *);
    if (!real_fn)
        real_fn = dlsym(RTLD_NEXT, "libusb_reset_device");
    int result = real_fn(dev);
    fprintf(stderr, "USB reset result=%d\n", result);
    return result;
}
