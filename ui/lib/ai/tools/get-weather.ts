import { tool } from 'ai';
import { z } from 'zod';

const weatherParams = z.object({
  latitude: z.number(),
  longitude: z.number(),
});

export const getWeather = tool({
  description: 'Get the current weather at a location',
  parameters: weatherParams,
  execute: async ({ latitude, longitude }) => {
    const response = await fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current=temperature_2m&hourly=temperature_2m&daily=sunrise,sunset&timezone=auto`,
    );

    const weatherData = await response.json();
    return weatherData;
  },
});
