/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */


/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

//COM_InitTypeDef BspCOMInit;
UART_HandleTypeDef hlpuart1;
DMA_HandleTypeDef hdma_lpuart1_tx;

SPI_HandleTypeDef hspi1;

/* USER CODE BEGIN PV */
#define ADS_NUM_CHANNELS   4
#define ADS_FRAME_BYTES    (3 + 3 * ADS_NUM_CHANNELS)

/* ADS1299 commands */
#define ADS_CMD_WAKEUP   0x02
#define ADS_CMD_STANDBY  0x04
#define ADS_CMD_RESET    0x06
#define ADS_CMD_START    0x08
#define ADS_CMD_STOP     0x0A
#define ADS_CMD_RDATAC   0x10
#define ADS_CMD_SDATAC   0x11
#define ADS_CMD_RDATA    0x12
#define ADS_CMD_RREG     0x20
#define ADS_CMD_WREG     0x40
#define ADS_NOP          0x00

/* Registers */
#define ADS_REG_ID       0x00
#define ADS_REG_CONFIG1  0x01
#define ADS_REG_CONFIG2  0x02
#define ADS_REG_CONFIG3  0x03
#define ADS_REG_LOFF     0x04
#define ADS_REG_CH1SET   0x05
#define ADS_REG_CH2SET   0x06
#define ADS_REG_CH3SET   0x07
#define ADS_REG_CH4SET   0x08
#define ADS_REG_CH5SET   0x09
#define ADS_REG_CH6SET   0x0A
#define ADS_REG_CH7SET   0x0B
#define ADS_REG_CH8SET   0x0C
#define ADS_REG_LOFF_SENSP   0x0F
#define ADS_REG_LOFF_SENSN   0x10
#define ADS_REG_LOFF_FLIP    0x11
#define ADS_REG_LOFF_STATP   0x12
#define ADS_REG_LOFF_STATN   0x13
#define ADS_REG_GPIO         0x14

/* Bias Registers*/
#define ADS_REG_BIAS_SENSP 0x0D
#define ADS_REG_BIAS_SENSN 0x0E
#define ADS_REG_MISC1      0x15
#define ADS_REG_MISC2      0x16
#define ADS_REG_CONFIG4    0x17

/*Channel commands*/
#define ADS_CH_PD_ON           0x00
#define ADS_CH_PD_OFF          0x80

#define ADS_CH_GAIN_1          0x00
#define ADS_CH_GAIN_2          0x10
#define ADS_CH_GAIN_4          0x20
#define ADS_CH_GAIN_6          0x30
#define ADS_CH_GAIN_8          0x40
#define ADS_CH_GAIN_12         0x50
#define ADS_CH_GAIN_24         0x60

#define ADS_CH_SRB2_OFF        0x00
#define ADS_CH_SRB2_ON         0x08

#define ADS_CH_MUX_NORMAL      0x00
#define ADS_CH_MUX_SHORTED     0x01
#define ADS_CH_MUX_BIAS_MEAS   0x02
#define ADS_CH_MUX_MVDD        0x03
#define ADS_CH_MUX_TEMP        0x04
#define ADS_CH_MUX_TEST        0x05
#define ADS_CH_MUX_BIAS_DRP    0x06
#define ADS_CH_MUX_BIAS_DRN    0x07

/*DMA stuff*/
static uint32_t dma_tx_start_tick = 0;

#define UART_DMA_BUF_SIZE 192

static char     dma_active_buf[UART_DMA_BUF_SIZE];
static char     dma_pending_buf[UART_DMA_BUF_SIZE];

static volatile uint8_t dma_tx_busy = 0;
static volatile uint8_t dma_pending_ready = 0;

volatile uint32_t drdy_count = 0;


static volatile uint8_t stream_enabled = 0;
static volatile uint32_t g_frame_count = 0;

#define UART_RX_LINE_MAX 64
static char uart_rx_line[UART_RX_LINE_MAX];
static uint32_t uart_rx_idx = 0;

static volatile uint8_t contact_mode_enabled = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
void PeriphCommonClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_LPUART1_UART_Init(void);
static void MX_SPI1_Init(void);
/* USER CODE BEGIN PFP */
static uint8_t ADS_MakeChSet(uint8_t pd, uint8_t gain, uint8_t srb2, uint8_t mux);
static void uart_print(const char *s);
static inline void ADS_CS_LOW(void);
static inline void ADS_CS_HIGH(void);
static void ADS_SmallDelay(void);
static void ADS_GPIO_InitPins(void);
static void ADS_SendCommand(uint8_t cmd);
static uint8_t ADS_ReadReg(uint8_t reg);
static void ADS_WriteReg(uint8_t reg, uint8_t value);
static void ADS1299_Init(void);
static uint8_t ADS_ReadFrame(int32_t ch_raw[ADS_NUM_CHANNELS]);
static void ADS_PrintRegisters(void);
static void ADS_StreamFrameCSV(uint32_t frame_count, const int32_t ch_raw[ADS_NUM_CHANNELS]);

static void UART_PollCommands(void);
static void ProcessHostCommand(const char *line);
static void STM_SendInfo(const char *msg);
static void STM_SendEvent(uint32_t trial_num, uint32_t event_code, const char *event_name);

static void ADS_EnableLeadOff(void);
static void ADS_DisableLeadOff(void);
static void ADS_PrintLeadOffStatus(void);

static void UART_DMA_Init(void);
static void uart_print_dma(const char *s);


/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

static uint8_t ADS_MakeChSet(uint8_t pd, uint8_t gain, uint8_t srb2, uint8_t mux)
{
    return (uint8_t)(pd | gain | srb2 | mux);
}
static void uart_print(const char *s)
{
    HAL_UART_Transmit(&hlpuart1, (uint8_t *)s, (uint16_t)strlen(s), 100);
}

static inline void ADS_CS_LOW(void)
{
    HAL_GPIO_WritePin(CS_STM_GPIO_Port, CS_STM_Pin, GPIO_PIN_RESET);
}

static inline void ADS_CS_HIGH(void)
{
    HAL_GPIO_WritePin(CS_STM_GPIO_Port, CS_STM_Pin, GPIO_PIN_SET);
}

static void ADS_SmallDelay(void)
{
    for (volatile uint32_t i = 0; i < 200; i++)
    {
        __NOP();
    }
}

static void ADS_GPIO_InitPins(void)
{
    HAL_GPIO_WritePin(CS_STM_GPIO_Port, CS_STM_Pin, GPIO_PIN_SET);         // CS idle high
    HAL_GPIO_WritePin(PWDN_STM_GPIO_Port, PWDN_STM_Pin, GPIO_PIN_SET);     // not in power-down
    HAL_GPIO_WritePin(START_STM_GPIO_Port, START_STM_Pin, GPIO_PIN_RESET); // START low initially
}

static void ADS_SendCommand(uint8_t cmd)
{
    ADS_CS_LOW();
    HAL_SPI_Transmit(&hspi1, &cmd, 1, 50);
    ADS_SmallDelay();
    ADS_CS_HIGH();
}

static uint8_t ADS_ReadReg(uint8_t reg)
{
    uint8_t cmd[2];
    uint8_t rx = 0;
    uint8_t dummy = 0x00;

    cmd[0] = ADS_CMD_RREG | (reg & 0x1F);
    cmd[1] = 0x00;  // read 1 register

    ADS_CS_LOW();
    HAL_SPI_Transmit(&hspi1, cmd, 2, 50);
    ADS_SmallDelay();
    HAL_SPI_TransmitReceive(&hspi1, &dummy, &rx, 1, 50);
    ADS_CS_HIGH();

    return rx;
}

static void ADS_WriteReg(uint8_t reg, uint8_t value)
{
    uint8_t cmd[2];
    cmd[0] = ADS_CMD_WREG | (reg & 0x1F);
    cmd[1] = 0x00;  // write 1 register

    ADS_CS_LOW();
    HAL_SPI_Transmit(&hspi1, cmd, 2, 50);
    ADS_SmallDelay();
    HAL_SPI_Transmit(&hspi1, &value, 1, 50);
    ADS_SmallDelay();
    ADS_CS_HIGH();
}

static void ADS_PrintRegisters(void)
{
    char msg[192];
    uint8_t id   = ADS_ReadReg(ADS_REG_ID);
    uint8_t c1   = ADS_ReadReg(ADS_REG_CONFIG1);
    uint8_t c2   = ADS_ReadReg(ADS_REG_CONFIG2);
    uint8_t c3   = ADS_ReadReg(ADS_REG_CONFIG3);
    uint8_t m1   = ADS_ReadReg(ADS_REG_MISC1);
    uint8_t ch1  = ADS_ReadReg(ADS_REG_CH1SET);
    uint8_t ch2  = ADS_ReadReg(ADS_REG_CH2SET);
    uint8_t ch3  = ADS_ReadReg(ADS_REG_CH3SET);
    uint8_t ch4  = ADS_ReadReg(ADS_REG_CH4SET);
//    uint8_t ch5  = ADS_ReadReg(ADS_REG_CH5SET);
//    uint8_t ch6  = ADS_ReadReg(ADS_REG_CH6SET);
//    uint8_t ch7  = ADS_ReadReg(ADS_REG_CH7SET);
//    uint8_t ch8  = ADS_ReadReg(ADS_REG_CH8SET);

    snprintf(msg, sizeof(msg),
             "ADS REGS: ID=0x%02X C1=0x%02X C2=0x%02X C3=0x%02X M1=0x%02X "
             "CH1=0x%02X CH2=0x%02X CH3=0x%02X CH4=0x%02X\r\n",
             id, c1, c2, c3, m1,
             ch1, ch2, ch3, ch4);
    uart_print(msg);
}

static void ADS1299_Init(void)
{
    uart_print("ADS init start\r\n");

    ADS_GPIO_InitPins();
    HAL_Delay(10);

    /* Hardware reset through PWDN */
    HAL_GPIO_WritePin(PWDN_STM_GPIO_Port, PWDN_STM_Pin, GPIO_PIN_RESET);
    HAL_Delay(10);
    HAL_GPIO_WritePin(PWDN_STM_GPIO_Port, PWDN_STM_Pin, GPIO_PIN_SET);
    HAL_Delay(50);

    /* Software reset */
    ADS_SendCommand(ADS_CMD_RESET);
    HAL_Delay(5);

    /* Device wakes in RDATAC, must stop it before register access */
    ADS_SendCommand(ADS_CMD_SDATAC);
    HAL_Delay(2);

    /* Global config */
    ADS_WriteReg(ADS_REG_CONFIG1, 0x96);   // 250 SPS
    ADS_WriteReg(ADS_REG_CONFIG2, 0xC0);
    ADS_WriteReg(ADS_REG_CONFIG3, 0xEC);   // internal ref + bias amp enabled
    ADS_WriteReg(ADS_REG_LOFF,    0x00);   // lead-off off for now
    ADS_WriteReg(ADS_REG_CONFIG4, 0x00);   // continuous conversion

    /* Enable SRB1 to all channel inverting inputs */
    ADS_WriteReg(ADS_REG_MISC1, 0x20);

    /* Bias sense selection:
       choose active channels CH1-CH3 to contribute to bias generation.
       If CH4 is populated and used, change to 0x0F.
    */
    ADS_WriteReg(ADS_REG_BIAS_SENSP, 0x07);   // CH1P, CH2P, CH3P
    ADS_WriteReg(ADS_REG_BIAS_SENSN, 0x07);   // CH1N, CH2N, CH3N

    /* Channel setup:
       CH1 = C3
       CH2 = Cz
       CH3 = C4
       CH4 = optional spare (motor area nearby or debug electrode)
       SRB2 OFF because using SRB1 common reference
    */
//    ADS_WriteReg(ADS_REG_CH1SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));
//    ADS_WriteReg(ADS_REG_CH2SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));
//    ADS_WriteReg(ADS_REG_CH3SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));
//    ADS_WriteReg(ADS_REG_CH4SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));
    ADS_WriteReg(ADS_REG_CH1SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_12, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));
    ADS_WriteReg(ADS_REG_CH2SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_12, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));
    ADS_WriteReg(ADS_REG_CH3SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_12, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));
    ADS_WriteReg(ADS_REG_CH4SET, ADS_MakeChSet(ADS_CH_PD_ON,  ADS_CH_GAIN_12, ADS_CH_SRB2_OFF, ADS_CH_MUX_NORMAL));

    /* Unused channels powered down and input-shorted */
//    ADS_WriteReg(ADS_REG_CH5SET, ADS_MakeChSet(ADS_CH_PD_OFF, ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_SHORTED));
//    ADS_WriteReg(ADS_REG_CH6SET, ADS_MakeChSet(ADS_CH_PD_OFF, ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_SHORTED));
//    ADS_WriteReg(ADS_REG_CH7SET, ADS_MakeChSet(ADS_CH_PD_OFF, ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_SHORTED));
//    ADS_WriteReg(ADS_REG_CH8SET, ADS_MakeChSet(ADS_CH_PD_OFF, ADS_CH_GAIN_24, ADS_CH_SRB2_OFF, ADS_CH_MUX_SHORTED));

    ADS_PrintRegisters();

    /* Start conversions */
    ADS_SendCommand(ADS_CMD_START);
    HAL_Delay(1);
    ADS_SendCommand(ADS_CMD_RDATAC);
    HAL_Delay(1);

    uart_print("ADS init done\r\n");
}

static uint8_t ADS_ReadFrame(int32_t ch_raw[ADS_NUM_CHANNELS])
{
    uint8_t tx[ADS_FRAME_BYTES];
    uint8_t rx[ADS_FRAME_BYTES];

    memset(tx, ADS_NOP, sizeof(tx));

    ADS_CS_LOW();
    if (HAL_SPI_TransmitReceive(&hspi1, tx, rx, ADS_FRAME_BYTES, 100) != HAL_OK)
    {
        ADS_CS_HIGH();
        return 0;
    }
    ADS_CS_HIGH();

    for (int ch = 0; ch < ADS_NUM_CHANNELS; ch++)
    {
        uint8_t b0 = rx[3 + 3 * ch];
        uint8_t b1 = rx[3 + 3 * ch + 1];
        uint8_t b2 = rx[3 + 3 * ch + 2];

        uint32_t raw = ((uint32_t)b0 << 16) | ((uint32_t)b1 << 8) | b2;

        if (raw & 0x800000)
        {
            raw |= 0xFF000000;
        }

        ch_raw[ch] = (int32_t)raw;
    }

    return 1;
}


static void ADS_StreamFrameCSV(uint32_t frame_count, const int32_t ch_raw[ADS_NUM_CHANNELS])
{
    char msg[192];

    snprintf(msg, sizeof(msg),
             "D,%lu,%lu,%ld,%ld,%ld,%ld\r\n",
             (unsigned long)frame_count,
             (unsigned long)HAL_GetTick(),
             (long)ch_raw[0],   // C3
             (long)ch_raw[1],   // Cz
             (long)ch_raw[2],   // C4
             (long)ch_raw[3]);  // CH4

    uart_print_dma(msg);
}


static void STM_SendInfo(const char *msg)
{
    char out[128];
    snprintf(out, sizeof(out), "I,%s\r\n", msg);
    uart_print_dma(out);
}

static void STM_SendEvent(uint32_t trial_num, uint32_t event_code, const char *event_name)
{
    char out[160];
    snprintf(out, sizeof(out),
             "E,%lu,%lu,%lu,%lu,%s\r\n",
             (unsigned long)g_frame_count,
             (unsigned long)HAL_GetTick(),
             (unsigned long)trial_num,
             (unsigned long)event_code,
             event_name);
    uart_print_dma(out);
}

static void ProcessHostCommand(const char *line)
{
	if (strcmp(line, "START") == 0)
	{
	    if (contact_mode_enabled)
	    {
	        STM_SendInfo("CONTACT_MODE_ACTIVE");
	        return;
	    }

	    g_frame_count = 0;
	    drdy_count = 0;
	    stream_enabled = 1;
	    STM_SendInfo("RUN_START");

	    //Temporary DRDY check
//	    HAL_Delay(100);
//		stream_enabled = 0;
//		char dbg[48];
//		snprintf(dbg, sizeof(dbg), "DRDY_100MS=%lu", (unsigned long)drdy_count);
//		STM_SendInfo(dbg);
//		stream_enabled = 1;

	    return;
	}

    if (strcmp(line, "STOP") == 0)
    {
        stream_enabled = 0;
        STM_SendInfo("RUN_END");
        return;
    }

    if (strcmp(line, "CONTACT_ON") == 0)
    {
        ADS_EnableLeadOff();
        return;
    }

    if (strcmp(line, "CONTACT_OFF") == 0)
    {
        ADS_DisableLeadOff();
        return;
    }

    if (strcmp(line, "CONTACT_STATUS") == 0)
    {
    	if (stream_enabled)
    	    {
    	        STM_SendInfo("CONTACT_STATUS_BLOCKED_DURING_STREAM");
    	        return;
    	    }
    	    ADS_PrintLeadOffStatus();
    	    return;
    }

    if (strncmp(line, "MARK,", 5) == 0)
    {
        uint32_t trial_num = 0;
        uint32_t event_code = 0;
        char event_name[48];

        if (sscanf(line, "MARK,%lu,%lu,%47[^\r\n]",
                   (unsigned long *)&trial_num,
                   (unsigned long *)&event_code,
                   event_name) == 3)
        {
            STM_SendEvent(trial_num, event_code, event_name);
        }
        else
        {
            STM_SendInfo("BAD_MARK");
        }
        return;
    }

    STM_SendInfo("UNKNOWN_CMD");
}

static void UART_PollCommands(void)
{
    uint8_t ch;

    while (HAL_UART_Receive(&hlpuart1, &ch, 1, 0) == HAL_OK)
    {
        if (ch == '\r')
        {
            continue;
        }
        else if (ch == '\n')
        {
            uart_rx_line[uart_rx_idx] = '\0';

            if (uart_rx_idx > 0)
            {
                ProcessHostCommand(uart_rx_line);
            }

            uart_rx_idx = 0;
        }
        else
        {
            if (uart_rx_idx < (UART_RX_LINE_MAX - 1))
            {
                uart_rx_line[uart_rx_idx++] = (char)ch;
            }
            else
            {
                uart_rx_idx = 0;
                STM_SendInfo("RX_OVERFLOW");
            }
        }
    }
}




static void ADS_EnableLeadOff(void)
{
    stream_enabled = 0;

    ADS_SendCommand(ADS_CMD_SDATAC);
    HAL_Delay(2);

    ADS_WriteReg(ADS_REG_LOFF, 0x13);
    ADS_WriteReg(ADS_REG_LOFF_SENSP, 0x0F);
    ADS_WriteReg(ADS_REG_LOFF_SENSN, 0x0F);
    ADS_WriteReg(ADS_REG_LOFF_FLIP, 0x00);

    ADS_SendCommand(ADS_CMD_RDATAC);
    HAL_Delay(2);

    contact_mode_enabled = 1;
    STM_SendInfo("CONTACT_ON");
}

static void ADS_DisableLeadOff(void)
{
    ADS_SendCommand(ADS_CMD_SDATAC);
    HAL_Delay(2);

    ADS_WriteReg(ADS_REG_LOFF, 0x00);
    ADS_WriteReg(ADS_REG_LOFF_SENSP, 0x00);
    ADS_WriteReg(ADS_REG_LOFF_SENSN, 0x00);
    ADS_WriteReg(ADS_REG_LOFF_FLIP, 0x00);

    ADS_SendCommand(ADS_CMD_RDATAC);
    HAL_Delay(2);

    contact_mode_enabled = 0;
    STM_SendInfo("CONTACT_OFF");
}

static void ADS_PrintLeadOffStatus(void)
{
    char msg[160];
    uint8_t statp;
    uint8_t statn;

    ADS_SendCommand(ADS_CMD_SDATAC);
    HAL_Delay(2);

    statp = ADS_ReadReg(ADS_REG_LOFF_STATP);
    statn = ADS_ReadReg(ADS_REG_LOFF_STATN);

    ADS_SendCommand(ADS_CMD_RDATAC);
    HAL_Delay(2);

    /*
      For CH1-CH4:
      bit0 -> CH1
      bit1 -> CH2
      bit2 -> CH3
      bit3 -> CH4

      We print both raw register bytes and a simple per-channel summary.
    */
    snprintf(msg, sizeof(msg),
             "CONTACT_RAW,STATP=0x%02X,STATN=0x%02X",
             statp, statn);
    STM_SendInfo(msg);

    snprintf(msg, sizeof(msg),
             "CONTACT_CH,C3,%s,Cz,%s,C4,%s,CH4,%s",
             ((statp & 0x01) || (statn & 0x01)) ? "OFF" : "OK",
             ((statp & 0x02) || (statn & 0x02)) ? "OFF" : "OK",
             ((statp & 0x04) || (statn & 0x04)) ? "OFF" : "OK",
             ((statp & 0x08) || (statn & 0x08)) ? "OFF" : "OK");
    STM_SendInfo(msg);
}


static void UART_DMA_Init(void) {
	dma_tx_busy = 0;
	dma_pending_ready = 0;
}


static void uart_print_dma(const char *s) {
	uint16_t len = (uint16_t)strlen(s);
	    if (len == 0) return;
	    if (len >= UART_DMA_BUF_SIZE)
	        len = UART_DMA_BUF_SIZE - 1;

	    __disable_irq();

	    if (!dma_tx_busy)
	    {
	        memcpy(dma_active_buf, s, len);
	        dma_active_buf[len] = '\0';
	        dma_tx_busy = 1;
	        dma_tx_start_tick = HAL_GetTick();
	        __enable_irq();

	        HAL_StatusTypeDef st =
	            HAL_UART_Transmit_DMA(&hlpuart1, (uint8_t *)dma_active_buf, len);
	        if (st != HAL_OK)
	        {
	            __disable_irq();
	            dma_tx_busy = 0;
	            __enable_irq();
	        }
	    }
	    else
	    {
	        memcpy(dma_pending_buf, s, len);
	        dma_pending_buf[len] = '\0';
	        dma_pending_ready = 1;
	        __enable_irq();
	    }
}


/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* Configure the peripherals common clocks */
  PeriphCommonClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_LPUART1_UART_Init();
  MX_SPI1_Init();
  /* USER CODE BEGIN 2 */
  UART_DMA_Init();
  uart_print("\r\nWB55 boot\r\n");
  uart_print("Starting ADS1299 bring-up...\r\n");

  ADS1299_Init();
  STM_SendInfo("READY");

  int32_t ch_raw[ADS_NUM_CHANNELS];
  /* USER CODE END 2 */

//  /* Initialize leds */
//  BSP_LED_Init(LED_BLUE);
//  BSP_LED_Init(LED_GREEN);
//  BSP_LED_Init(LED_RED);
//
//  /* Initialize USER push-button, will be used to trigger an interrupt each time it's pressed.*/
//  BSP_PB_Init(BUTTON_SW1, BUTTON_MODE_EXTI);
//  BSP_PB_Init(BUTTON_SW2, BUTTON_MODE_EXTI);
//  BSP_PB_Init(BUTTON_SW3, BUTTON_MODE_EXTI);
//
//  /* Initialize COM1 port (115200, 8 bits (7-bit data + 1 stop bit), no parity */
//  BspCOMInit.BaudRate   = 115200;
//  BspCOMInit.WordLength = COM_WORDLENGTH_8B;
//  BspCOMInit.StopBits   = COM_STOPBITS_1;
//  BspCOMInit.Parity     = COM_PARITY_NONE;
//  BspCOMInit.HwFlowCtl  = COM_HWCONTROL_NONE;
//  if (BSP_COM_Init(COM1, &BspCOMInit) != BSP_ERROR_NONE)
//  {
//    Error_Handler();
//  }

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */

	  if (dma_tx_busy && (HAL_GetTick() - dma_tx_start_tick) > 50)
	  {
	      HAL_UART_AbortTransmit(&hlpuart1);
	      __disable_irq();
	      dma_tx_busy = 0;
	      dma_pending_ready = 0;
	      __enable_irq();
	  }

	  UART_PollCommands();

	      if (stream_enabled)
	      {
	          uint8_t got_sample = 0;
	          uint32_t backlog = 0;

	          __disable_irq();
	          if (drdy_count > 0)
	          {
	              drdy_count--;
	              backlog = drdy_count;
	              got_sample = 1;
	          }
	          __enable_irq();

	          if (got_sample)
	          {
	              if (backlog > 0)
	                  uart_print_dma("I,SAMPLE_LAG\r\n");

	              if (ADS_ReadFrame(ch_raw))
	              {
	                  ADS_StreamFrameCSV(g_frame_count, ch_raw);
	                  g_frame_count++;
	              }
	              else
	              {
	                  uart_print_dma("I,ADS_ReadFrame_failed\r\n");
	              }
	          }
	      }

  /* USER CODE END 3 */
}

}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI|RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.MSIState = RCC_MSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.MSICalibrationValue = RCC_MSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.MSIClockRange = RCC_MSIRANGE_10;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure the SYSCLKSource, HCLK, PCLK1 and PCLK2 clocks dividers
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK4|RCC_CLOCKTYPE_HCLK2
                              |RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_MSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.AHBCLK2Divider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.AHBCLK4Divider = RCC_SYSCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief Peripherals Common Clock Configuration
  * @retval None
  */
void PeriphCommonClock_Config(void)
{
  RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

  /** Initializes the peripherals clock
  */
  PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_SMPS;
  PeriphClkInitStruct.SmpsClockSelection = RCC_SMPSCLKSOURCE_HSI;
  PeriphClkInitStruct.SmpsDivSelection = RCC_SMPSCLKDIV_RANGE0;

  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN Smps */

  /* USER CODE END Smps */
}

/**
  * @brief LPUART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_LPUART1_UART_Init(void)
{

  /* USER CODE BEGIN LPUART1_Init 0 */

  /* USER CODE END LPUART1_Init 0 */

  /* USER CODE BEGIN LPUART1_Init 1 */

  /* USER CODE END LPUART1_Init 1 */
  hlpuart1.Instance = LPUART1;
  hlpuart1.Init.BaudRate = 460800;
  hlpuart1.Init.WordLength = UART_WORDLENGTH_8B;
  hlpuart1.Init.StopBits = UART_STOPBITS_1;
  hlpuart1.Init.Parity = UART_PARITY_NONE;
  hlpuart1.Init.Mode = UART_MODE_TX_RX;
  hlpuart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  hlpuart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  hlpuart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  hlpuart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  hlpuart1.FifoMode = UART_FIFOMODE_DISABLE;
  if (HAL_UART_Init(&hlpuart1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetTxFifoThreshold(&hlpuart1, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetRxFifoThreshold(&hlpuart1, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_DisableFifoMode(&hlpuart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN LPUART1_Init 2 */

  /* USER CODE END LPUART1_Init 2 */

}

/**
  * @brief SPI1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_SPI1_Init(void)
{

  /* USER CODE BEGIN SPI1_Init 0 */

  /* USER CODE END SPI1_Init 0 */

  /* USER CODE BEGIN SPI1_Init 1 */

  /* USER CODE END SPI1_Init 1 */
  /* SPI1 parameter configuration*/
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_MASTER;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
  hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_2EDGE;
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_8;
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.CRCPolynomial = 7;
  hspi1.Init.CRCLength = SPI_CRC_LENGTH_DATASIZE;
  hspi1.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
  if (HAL_SPI_Init(&hspi1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN SPI1_Init 2 */

  /* USER CODE END SPI1_Init 2 */

}

/**
  * Enable DMA controller clock
  */
static void MX_DMA_Init(void)
{

  /* DMA controller clock enable */
  __HAL_RCC_DMAMUX1_CLK_ENABLE();
  __HAL_RCC_DMA1_CLK_ENABLE();

  /* DMA interrupt init */
  /* DMA1_Channel1_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(START_STM_GPIO_Port, START_STM_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, PWDN_STM_Pin|CS_STM_Pin, GPIO_PIN_SET);

  /*Configure GPIO pins : START_STM_Pin PWDN_STM_Pin CS_STM_Pin */
  GPIO_InitStruct.Pin = START_STM_Pin|PWDN_STM_Pin|CS_STM_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pin : DRDY_STM_Pin */
  GPIO_InitStruct.Pin = DRDY_STM_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(DRDY_STM_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pins : USB_DM_Pin USB_DP_Pin */
  GPIO_InitStruct.Pin = USB_DM_Pin|USB_DP_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  GPIO_InitStruct.Alternate = GPIO_AF10_USB;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI3_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(EXTI3_IRQn);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    if (GPIO_Pin == DRDY_STM_Pin)
    {
        drdy_count++;
    }
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
	if (huart->Instance == LPUART1)
	    {
	        if (dma_pending_ready)
	        {
	            memcpy(dma_active_buf, dma_pending_buf,
	                   strlen(dma_pending_buf) + 1);
	            dma_pending_ready = 0;
	            dma_tx_start_tick = HAL_GetTick();

	            HAL_StatusTypeDef st =
	                HAL_UART_Transmit_DMA(&hlpuart1,
	                                      (uint8_t *)dma_active_buf,
	                                      (uint16_t)strlen(dma_active_buf));
	            if (st != HAL_OK)
	                dma_tx_busy = 0;  // failed — release so next call can retry
	            // on success dma_tx_busy stays 1 until next callback
	        }
	        else
	        {
	            dma_tx_busy = 0;
	        }
	    }
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
