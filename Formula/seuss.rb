class Seuss < Formula
  desc "A DSL for modeling and visualizing temporal narratives"
  homepage "https://github.com/gongahkia/seuss"
  version "0.1.0"
  license "MIT"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/gongahkia/seuss/releases/download/v#{version}/seuss-v#{version}-aarch64-apple-darwin.tar.gz"
      sha256 "PLACEHOLDER"
    else
      url "https://github.com/gongahkia/seuss/releases/download/v#{version}/seuss-v#{version}-x86_64-apple-darwin.tar.gz"
      sha256 "PLACEHOLDER"
    end
  end

  on_linux do
    url "https://github.com/gongahkia/seuss/releases/download/v#{version}/seuss-v#{version}-x86_64-unknown-linux-gnu.tar.gz"
    sha256 "PLACEHOLDER"
  end

  def install
    bin.install "seuss"
  end

  test do
    assert_match "seuss", shell_output("#{bin}/seuss --version")
  end
end
