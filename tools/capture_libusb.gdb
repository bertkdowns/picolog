set pagination off
set breakpoint pending on
set environment USBTC08_LIBRARY=/opt/picoscope/lib/libusbtc08.so.2.0.0

set $in_ioctl = 0
catch syscall ioctl
commands
  silent
  if ($in_ioctl == 0)
    set $in_ioctl = 1
    set $usb_request = $rsi
    set $usb_argument = $rdx
    if ($usb_request == 0x8038550a)
      set $usb_urb = $usb_argument
      set $usb_endpoint = *(unsigned char *)($usb_urb + 1)
      set $usb_buffer = *(void **)($usb_urb + 16)
      set $usb_length = *(int *)($usb_urb + 24)
      printf "SUBMIT endpoint=0x%02x length=%d data=", $usb_endpoint, $usb_length
      if (($usb_endpoint & 0x80) == 0)
        x/64bx $usb_buffer
      else
        printf "<IN>\n"
      end
    end
  else
    set $in_ioctl = 0
    if (($usb_request == 0x4008550c) || ($usb_request == 0x4008550d))
      set $usb_urb = *(void **)$usb_argument
      if ($usb_urb > 0x10000)
        set $usb_endpoint = *(unsigned char *)($usb_urb + 1)
        set $usb_buffer = *(void **)($usb_urb + 16)
        set $usb_actual = *(int *)($usb_urb + 28)
        printf "REAP endpoint=0x%02x actual=%d data=", $usb_endpoint, $usb_actual
        x/64bx $usb_buffer
      end
    end
  end
  continue
end

run picologger/read_sdk.py --channel 5 --type T --mains 50
