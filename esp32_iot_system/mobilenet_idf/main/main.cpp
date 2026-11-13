#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <new>

#include "esp_camera.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_psram.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "driver/gpio.h"
#include "nvs_flash.h"
#include "img_converters.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/version.h"

#include "user_config.h"

extern const uint8_t model_start[] asm("_binary_best_potato_model_from_pth_int8_tflite_start");
extern const uint8_t model_end[] asm("_binary_best_potato_model_from_pth_int8_tflite_end");

namespace {
constexpr char TAG[] = "potato_mobilenet";
constexpr int kInputWidth = 224;
constexpr int kInputHeight = 224;
constexpr int kInputChannels = 3;
constexpr size_t kTensorArenaBytes = 2560 * 1024;
constexpr float kImageMean[kInputChannels] = {0.485f, 0.456f, 0.406f};
constexpr float kImageStd[kInputChannels] = {0.229f, 0.224f, 0.225f};
constexpr EventBits_t kWifiConnected = BIT0;

EventGroupHandle_t wifi_events;
uint8_t* tensor_arena = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
bool item_was_present = false;

bool init_camera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5;
  config.pin_d1 = 18;
  config.pin_d2 = 19;
  config.pin_d3 = 21;
  config.pin_d4 = 36;
  config.pin_d5 = 39;
  config.pin_d6 = 34;
  config.pin_d7 = 35;
  config.pin_xclk = 0;
  config.pin_pclk = 22;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_sccb_sda = 26;
  config.pin_sccb_scl = 27;
  config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;

  const esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Camera init failed: %s", esp_err_to_name(err));
    return false;
  }
  return true;
}

void wifi_event_handler(void*, esp_event_base_t event_base, int32_t event_id, void*) {
  if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
    esp_wifi_connect();
  } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
    xEventGroupClearBits(wifi_events, kWifiConnected);
    esp_wifi_connect();
  } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
    xEventGroupSetBits(wifi_events, kWifiConnected);
    ESP_LOGI(TAG, "Wi-Fi connected");
  }
}

void init_wifi() {
  ESP_ERROR_CHECK(esp_netif_init());
  ESP_ERROR_CHECK(esp_event_loop_create_default());
  esp_netif_create_default_wifi_sta();
  wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
  ESP_ERROR_CHECK(esp_wifi_init(&init_config));
  wifi_events = xEventGroupCreate();
  ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, nullptr));
  ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, nullptr));

  wifi_config_t wifi_config = {};
  strlcpy(reinterpret_cast<char*>(wifi_config.sta.ssid), WIFI_SSID, sizeof(wifi_config.sta.ssid));
  strlcpy(reinterpret_cast<char*>(wifi_config.sta.password), WIFI_PASSWORD, sizeof(wifi_config.sta.password));
  wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
  ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
  ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
  ESP_ERROR_CHECK(esp_wifi_start());
}

bool init_model() {
  const size_t model_bytes = static_cast<size_t>(model_end - model_start);
  const tflite::Model* model = tflite::GetModel(model_start);
  if (model == nullptr || model->version() != TFLITE_SCHEMA_VERSION) {
    ESP_LOGE(TAG, "Invalid TFLite model or schema version mismatch");
    return false;
  }

  // The TFLite interpreter reported seven builtin operators. DELEGATE is a
  // host-side XNNPACK delegate and is not part of the embedded model graph.
  static tflite::MicroMutableOpResolver<7> resolver;
  if (resolver.AddConv2D() != kTfLiteOk ||
      resolver.AddDepthwiseConv2D() != kTfLiteOk ||
      resolver.AddFullyConnected() != kTfLiteOk ||
      resolver.AddMean() != kTfLiteOk ||
      resolver.AddPad() != kTfLiteOk ||
      resolver.AddAdd() != kTfLiteOk ||
      resolver.AddQuantize() != kTfLiteOk) {
    ESP_LOGE(TAG, "Failed to register required TFLM operators");
    return false;
  }

  tensor_arena = static_cast<uint8_t*>(heap_caps_malloc(
      kTensorArenaBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (tensor_arena == nullptr) {
    ESP_LOGE(TAG, "Could not allocate %u-byte PSRAM tensor arena",
             static_cast<unsigned>(kTensorArenaBytes));
    return false;
  }

  interpreter = new (std::nothrow) tflite::MicroInterpreter(
      model, resolver, tensor_arena, kTensorArenaBytes, nullptr);
  if (interpreter == nullptr || interpreter->AllocateTensors() != kTfLiteOk) {
    ESP_LOGE(TAG, "TFLM AllocateTensors failed; increase arena or inspect supported ops");
    return false;
  }

  TfLiteTensor* input = interpreter->input(0);
  TfLiteTensor* output = interpreter->output(0);
  if (input->type != kTfLiteUInt8 || output->type != kTfLiteUInt8 ||
      input->dims->size != 4 || input->dims->data[1] != kInputHeight ||
      input->dims->data[2] != kInputWidth || input->dims->data[3] != kInputChannels ||
      output->dims->size != 2 || output->dims->data[1] != 2 || output->bytes < 2 ||
      input->params.scale <= 0.0f || output->params.scale <= 0.0f) {
    ESP_LOGE(TAG, "Model I/O must be uint8 [1,224,224,3] -> uint8 [1,2]");
    return false;
  }
  ESP_LOGI(TAG, "TFLM ready: model=%u bytes, tensor arena=%u bytes, input scale=%g zero=%d",
           static_cast<unsigned>(model_bytes), static_cast<unsigned>(kTensorArenaBytes),
           input->params.scale, input->params.zero_point);
  return true;
}

inline uint8_t quantize_pixel(uint8_t value, int channel, const TfLiteTensor* input) {
  // Match torchvision: ToTensor followed by ImageNet mean/std normalization.
  const float real_value = (static_cast<float>(value) / 255.0f - kImageMean[channel]) /
                           kImageStd[channel];
  const float quantized = std::round(real_value / input->params.scale + input->params.zero_point);
  return static_cast<uint8_t>(std::clamp(quantized, 0.0f, 255.0f));
}

bool resize_rgb_to_model(const uint8_t* source, int source_width, int source_height, TfLiteTensor* input) {
  if (source == nullptr || source_width <= 0 || source_height <= 0 || input == nullptr || input->data.uint8 == nullptr) {
    return false;
  }
  for (int y = 0; y < kInputHeight; ++y) {
    const float fy = std::max(0.0f, (y + 0.5f) * source_height / kInputHeight - 0.5f);
    const int y0 = std::min(static_cast<int>(fy), source_height - 1);
    const int y1 = std::min(y0 + 1, source_height - 1);
    const float wy = fy - y0;
    for (int x = 0; x < kInputWidth; ++x) {
      const float fx = std::max(0.0f, (x + 0.5f) * source_width / kInputWidth - 0.5f);
      const int x0 = std::min(static_cast<int>(fx), source_width - 1);
      const int x1 = std::min(x0 + 1, source_width - 1);
      const float wx = fx - x0;
      for (int channel = 0; channel < kInputChannels; ++channel) {
        const auto pixel = [&](int px, int py) {
          return source[(py * source_width + px) * kInputChannels + channel];
        };
        const float top = pixel(x0, y0) * (1.0f - wx) + pixel(x1, y0) * wx;
        const float bottom = pixel(x0, y1) * (1.0f - wx) + pixel(x1, y1) * wx;
        const uint8_t resized = static_cast<uint8_t>(std::clamp(
            std::round(top * (1.0f - wy) + bottom * wy), 0.0f, 255.0f));
        const size_t index = (y * kInputWidth + x) * kInputChannels + channel;
        input->data.uint8[index] = quantize_pixel(resized, channel, input);
      }
    }
  }
  return true;
}

void post_result(const char* quality, float confidence) {
  if ((xEventGroupGetBits(wifi_events) & kWifiConnected) == 0) {
    ESP_LOGW(TAG, "Wi-Fi unavailable; inference completed locally, result not uploaded");
    return;
  }
  char payload[160];
  std::snprintf(payload, sizeof(payload),
      "{\"device\":\"esp32-cam-mobilenet-int8\",\"quality\":\"%s\",\"confidence\":%.4f}",
      quality, confidence);
  esp_http_client_config_t config = {};
  config.url = BACKEND_RESULT_URL;
  config.method = HTTP_METHOD_POST;
  config.timeout_ms = 4000;
  esp_http_client_handle_t client = esp_http_client_init(&config);
  if (client == nullptr) {
    ESP_LOGE(TAG, "Could not create HTTP client");
    return;
  }
  esp_http_client_set_header(client, "Content-Type", "application/json");
  esp_http_client_set_post_field(client, payload, std::strlen(payload));
  const esp_err_t err = esp_http_client_perform(client);
  if (err == ESP_OK) {
    ESP_LOGI(TAG, "Dashboard POST status=%d", esp_http_client_get_status_code(client));
  } else {
    ESP_LOGW(TAG, "Dashboard POST failed: %s", esp_err_to_name(err));
  }
  esp_http_client_cleanup(client);
}

void capture_and_classify() {
  camera_fb_t* frame = esp_camera_fb_get();
  if (frame == nullptr) {
    ESP_LOGE(TAG, "Camera capture failed");
    return;
  }
  const size_t rgb_bytes = static_cast<size_t>(frame->width) * frame->height * 3;
  uint8_t* rgb = static_cast<uint8_t*>(heap_caps_malloc(rgb_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (rgb == nullptr) {
    esp_camera_fb_return(frame);
    ESP_LOGE(TAG, "Could not allocate RGB frame in PSRAM");
    return;
  }
  const bool decoded = fmt2rgb888(frame->buf, frame->len, frame->format, rgb);
  const int width = frame->width;
  const int height = frame->height;
  esp_camera_fb_return(frame);
  if (!decoded) {
    heap_caps_free(rgb);
    ESP_LOGE(TAG, "JPEG to RGB conversion failed");
    return;
  }

  TfLiteTensor* input = interpreter->input(0);
  if (!resize_rgb_to_model(rgb, width, height, input)) {
    heap_caps_free(rgb);
    ESP_LOGE(TAG, "Image preprocessing failed");
    return;
  }
  heap_caps_free(rgb);

  const int64_t start_us = esp_timer_get_time();
  if (interpreter->Invoke() != kTfLiteOk) {
    ESP_LOGE(TAG, "TFLM Invoke failed");
    return;
  }
  const int64_t inference_ms = (esp_timer_get_time() - start_us) / 1000;
  const TfLiteTensor* output = interpreter->output(0);
  const float logit_good =
      (static_cast<int>(output->data.uint8[0]) - output->params.zero_point) * output->params.scale;
  const float logit_poor =
      (static_cast<int>(output->data.uint8[1]) - output->params.zero_point) * output->params.scale;
  const bool is_poor = logit_poor > logit_good;
  const float max_logit = std::max(logit_good, logit_poor);
  const float exp_good = std::exp(logit_good - max_logit);
  const float exp_poor = std::exp(logit_poor - max_logit);
  const float confidence = is_poor ? exp_poor / (exp_good + exp_poor)
                                   : exp_good / (exp_good + exp_poor);
  const char* quality = is_poor ? "not_good" : "good";
  ESP_LOGI(TAG, "AI result=%s confidence=%.1f%% inference=%lldms",
           quality, confidence * 100.0f, inference_ms);
  post_result(quality, confidence);
}
}  // namespace

extern "C" void app_main(void) {
  ESP_ERROR_CHECK(nvs_flash_init());
  if (!esp_psram_is_initialized()) {
    ESP_LOGW(TAG, "PSRAM not initialized; camera/model memory may be insufficient");
  }

  if (!init_model()) {
    ESP_LOGE(TAG, "Model initialization failed");
    return;
  }
  if (!init_camera()) {
    ESP_LOGE(TAG, "Camera initialization failed");
    return;
  }

  gpio_config_t ir_config = {};
  ir_config.pin_bit_mask = 1ULL << IR_SENSOR_GPIO;
  ir_config.mode = GPIO_MODE_INPUT;
  ir_config.pull_up_en = GPIO_PULLUP_ENABLE;
  ir_config.pull_down_en = GPIO_PULLDOWN_DISABLE;
  ir_config.intr_type = GPIO_INTR_DISABLE;
  ESP_ERROR_CHECK(gpio_config(&ir_config));

  init_wifi();
  ESP_LOGI(TAG, "Ready. Model input is 224x224; place an item in front of the active-low IR sensor.");
  while (true) {
    const bool item_present = gpio_get_level(static_cast<gpio_num_t>(IR_SENSOR_GPIO)) == 0;
    if (item_present && !item_was_present) {
      vTaskDelay(pdMS_TO_TICKS(40));  // debounce the sensor edge
      if (gpio_get_level(static_cast<gpio_num_t>(IR_SENSOR_GPIO)) == 0) {
        item_was_present = true;
        capture_and_classify();
      }
    } else if (!item_present) {
      item_was_present = false;
    }
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}
