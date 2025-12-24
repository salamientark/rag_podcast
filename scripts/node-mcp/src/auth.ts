import * as jose from 'jose';

export async function createAuthToken(): Promise<string> {
  const privateKeyPem = process.env.MCP_PRIVATE_KEY;
  if (!privateKeyPem) {
    throw new Error('MCP_PRIVATE_KEY environment variable not set.');
  }

  try {
    // The private key might be in a single line in the .env file,
    // so we replace escaped newlines with actual newlines.
    const decodedKey = Buffer.from(privateKeyPem, 'base64').toString('utf8');
    const privateKey = await jose.importPKCS8(decodedKey, 'RS256');

    const jwt = await new jose.SignJWT({})
      .setProtectedHeader({ alg: 'RS256' })
      .setIssuedAt()
      .setIssuer('urn:notpatrick:client')
      .setAudience('urn:notpatrick:server')
      .setExpirationTime('1m')
      .sign(privateKey);

    return jwt;
  } catch (error) {
    console.error('Error creating auth token:', error);
    throw error;
  }
}
