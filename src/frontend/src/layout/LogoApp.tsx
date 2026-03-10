export default function LogoApp({ size = 26 }: { size?: number }) {
  return (
    <img
      src="/assets/logo-dictaphone-beta.svg"
      alt="Logo"
      width={size}
      height={size}
    />
  )
}
