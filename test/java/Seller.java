import java.io.*;
class Seller
{
  private int quantity;

  public Seller(int quantity)
  {
    this.quantity=quantity;
  }

  public int getQuantity()
  {
    return quantity;
  }

  public void setQuantity(int quantity)
  {
    this.quantity=quantity;
  }

  public int sell()
  {
    if(quantity>0)
    {
      quantity--;
      return 1;
    }
    else
    {
      return 0;
    }
  }
}
