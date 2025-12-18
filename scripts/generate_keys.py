from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_and_save_keys():
    """Generates an RSA key pair and saves them to .pem files."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Serialize private key in PKCS#8 format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize public key
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Save keys to files in the project root
    with open("private_key.pem", "wb") as f:
        f.write(private_pem)
    with open("public_key.pem", "wb") as f:
        f.write(public_pem)

    print(
        "✅ Successfully generated 'private_key.pem' and 'public_key.pem' in the project root."
    )
    print("\nNext steps:")
    print("1. Manually copy 'private_key.pem' to the 'mcp-client/' directory.")
    print("   cp private_key.pem mcp-client/private_key.pem")
    print(
        "2. The 'public_key.pem' is used by the server and should remain in the root."
    )
    print(
        "3. Ensure '*.pem' is added to your root .gitignore file to avoid committing keys."
    )


if __name__ == "__main__":
    generate_and_save_keys()
